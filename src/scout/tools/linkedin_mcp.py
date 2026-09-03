"""Attach `mcp-server-linkedin` as a set of tools.

The key architectural decision: the agent is given a **read-only subset**.
`send_message` and `connect_with_person` are not hidden behind a confirmation —
they are absent from the toolset entirely. An agent able to write to people on
the user's behalf is a separate class of risk that deserves its own design.

Filtering works from an allowlist rather than a denylist: if the server adds a
new writing tool, it cannot leak through to the agent on its own.

Two things about the server itself drive the rest of this module:

* It lists its whole toolset with no session at all, so the tool list says
  nothing about whether we are logged in. Session health is read from the
  `--status` subcommand instead.
* It defaults to importing a session out of any locally signed-in Chromium
  browser, which is refused here before the process is ever started.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool

from ..config import get_settings

logger = logging.getLogger(__name__)

READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "search_jobs",
        "get_job_details",
        "get_person_profile",
        "get_company_profile",
        "get_company_employees",
        "search_people",
    }
)
# The recommended-jobs feed has no tool in server 4.23.3 and is therefore a
# capability the agent simply does not have. `get_saved_jobs` is not a stand-in:
# it returns jobs the account explicitly saved, which is a different thing.

# Listed explicitly so refusals are readable in logs and tests.
FORBIDDEN_TOOLS: frozenset[str] = frozenset({"send_message", "connect_with_person"})

# Load-bearing for security, not a preference. Upstream defaults
# AUTO_IMPORT_FROM_BROWSER to on: without this flag the server scans every
# Chromium-family browser on the machine, picks the most recent live LinkedIn
# session, decrypts its cookies and adopts it. On this machine that is the
# owner's real profile, which is exactly what the burner account exists to avoid.
# The environment variable route is not available as a backstop, because the MCP
# stdio client forwards only HOME, PATH, USER, SHELL, TERM and LOGNAME to the
# child process. The command line is the only control we have.
REQUIRED_LAUNCH_FLAG = "--no-auto-import"

# Flags deciding which browser profile the server uses. A health check that looks
# at a different profile than the server will answer a question we did not ask.
_PROFILE_FLAGS: frozenset[str] = frozenset({"--user-data-dir", "--chrome-path"})

# `--status` launches a headless browser when a stored profile exists, so it is
# not instantaneous. The bound matters more than the exact value: a run must not
# be able to stall on a session check.
STATUS_TIMEOUT_SECONDS = 30.0


class UnsafeLinkedInCommandError(RuntimeError):
    """The configured launch command is missing a flag we refuse to start without."""


@dataclass(frozen=True)
class LinkedInHealth:
    """Verdict of the `--status` probe, with the server's own wording kept."""

    authenticated: bool
    detail: str


_health: LinkedInHealth | None = None
_health_lock: asyncio.Lock | None = None
_health_lock_loop: asyncio.AbstractEventLoop | None = None
_degradation: str | None = None


def _probe_lock() -> asyncio.Lock:
    """One probe at a time, in whichever loop is running.

    Built lazily rather than at import: an `asyncio.Lock` binds to the loop it
    first blocks on, so a module-level one starts raising as soon as a second
    loop touches it — a second `asyncio.run`, or the next test.
    """
    global _health_lock, _health_lock_loop
    loop = asyncio.get_running_loop()
    if _health_lock is None or _health_lock_loop is not loop:
        _health_lock = asyncio.Lock()
        _health_lock_loop = loop
    return _health_lock


def linkedin_degradation_note() -> str | None:
    """Why LinkedIn tools are missing, phrased for the user.

    `None` means the last `build_linkedin_tools()` call attached them. Callers
    that produce user-facing output are expected to pass this on: without it a
    run that collected nothing from LinkedIn is indistinguishable from one that
    found nothing there.
    """
    return _degradation


def _degrade(reason: str) -> list[BaseTool]:
    global _degradation
    _degradation = reason
    logger.warning("Running without LinkedIn tools. %s", reason)
    return []


def _command_parts() -> list[str] | None:
    """The configured launch command, split into argv. `None` when unconfigured."""
    settings = get_settings()
    if not settings.has_linkedin:
        return None
    parts = shlex.split(settings.scout_linkedin_mcp_command or "")
    return parts or None


def ensure_safe_command(parts: list[str]) -> None:
    """Refuse a launch command that would let the server adopt a browser session.

    Args:
        parts: the launch command split into argv.

    Raises:
        UnsafeLinkedInCommandError: when `--no-auto-import` is absent.
    """
    if REQUIRED_LAUNCH_FLAG in parts:
        return
    raise UnsafeLinkedInCommandError(
        f"REFUSING TO START THE LINKEDIN MCP SERVER: SCOUT_LINKEDIN_MCP_COMMAND is missing the "
        f"mandatory {REQUIRED_LAUNCH_FLAG} flag. Configured command: {shlex.join(parts)!r}. "
        f"Without that flag the server imports a LinkedIn session from any locally signed-in "
        f"Chromium browser on first use, which would hijack the owner's real profile instead of "
        f"the burner account. Add {REQUIRED_LAUNCH_FLAG} to the command; the "
        f"AUTO_IMPORT_FROM_BROWSER environment variable is not a substitute, because the MCP "
        f"stdio client does not forward it to the server process."
    )


def build_status_command(parts: list[str]) -> list[str]:
    """Turn a launch command into the `--status` probe for the same profile.

    Only the flags selecting a browser profile are carried over. Transport and
    timeout flags are irrelevant to a one-shot check, and `--no-auto-import` is
    re-applied because `--status` opens the browser too.

    Args:
        parts: the launch command split into argv.

    Returns:
        The argv of the probe.
    """
    command = [parts[0], "--status", REQUIRED_LAUNCH_FLAG]

    index = 1
    while index < len(parts):
        argument = parts[index]
        flag = argument.split("=", 1)[0]
        if flag in _PROFILE_FLAGS:
            if "=" in argument:
                command.append(argument)
            elif index + 1 < len(parts):
                command.extend((argument, parts[index + 1]))
                index += 1
        index += 1

    return command


# The markers the server puts on the line that actually states the verdict.
_VERDICT_MARKERS = ("❌", "✅", "⚠️", "ℹ️")


def _verdict_line(output: str, returncode: int | None) -> str:
    """Pull the verdict out of `--status` output.

    Taking the first line only works when no profile exists. Once one does, the
    command prints a header first — runtime, login generation, profile mode —
    and the first line names the runtime rather than the reason. That is exactly
    the expired-session case, where the reason is the thing the user needs.

    Args:
        output: everything the probe wrote, stdout and stderr combined.
        returncode: the probe's exit code, used only when it said nothing at all.

    Returns:
        The line carrying a status marker; failing that the last line, which is
        nearer the verdict than the first.
    """
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return f"`--status` exited {returncode}"
    for line in lines:
        if line.startswith(_VERDICT_MARKERS):
            return line
    return lines[-1]


async def probe_session(
    parts: list[str],
    # The bound belongs here rather than in a cancel scope at the call site: on
    # expiry this also has to kill the child, which cancellation alone would not.
    timeout_seconds: float = STATUS_TIMEOUT_SECONDS,
) -> LinkedInHealth:
    """Ask the server whether a usable session exists.

    Ground truth from mcp-server-linkedin 4.23.3: `--status` writes everything to
    stdout and leaves stderr empty. It exits 0 on `Session is valid (profile: …)`
    and exits 1 on `No valid source session found at …`, on `Session expired or
    invalid (profile: …)` and on a validation error. The exit code is therefore
    the signal, and the text is kept only so the reason is legible to the user.

    One case is optimistic by the server's own admission: on a foreign runtime it
    prints that the source cookie was not verified and still exits 0. That is a
    weaker guarantee than the rest, and the tool results remain the backstop.

    Args:
        parts: the launch command split into argv.
        timeout_seconds: how long to wait before giving up on the probe.

    Returns:
        The verdict. Anything other than a clean exit 0 counts as unauthenticated:
        a probe we could not run is not evidence of a working session.
    """
    command = build_status_command(parts)

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return LinkedInHealth(False, f"could not run {command[0]!r}: {exc}")

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_seconds)
    except TimeoutError:
        try:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            pass
        return LinkedInHealth(False, f"`--status` gave no answer within {timeout_seconds:.0f}s")

    output = (stdout + stderr).decode("utf-8", errors="replace").strip()
    return LinkedInHealth(process.returncode == 0, _verdict_line(output, process.returncode))


async def linkedin_health(parts: list[str], *, refresh: bool = False) -> LinkedInHealth:
    """Probe the session once per process and reuse the verdict.

    `build_linkedin_tools()` is called from the agent, from the research subgraph
    and from profile ingestion. Probing on each of them would launch a headless
    browser three times over for one answer.

    Args:
        parts: the launch command split into argv.
        refresh: run the probe again instead of reusing a cached verdict.

    Returns:
        The verdict.
    """
    global _health
    async with _probe_lock():
        if _health is None or refresh:
            _health = await probe_session(parts)
        return _health


def reset_linkedin_health() -> None:
    """Forget the cached session verdict and degradation reason.

    The next `build_linkedin_tools()` call probes again. Used by tests and by
    anything that wants a second opinion after a re-login.
    """
    global _health, _degradation
    _health = None
    _degradation = None


def _block_text(block: Any) -> str | None:
    """Text out of one MCP content block, whether it arrives as a dict or an object."""
    if isinstance(block, str):
        return block
    if isinstance(block, dict):
        text = block.get("text")
        return text if isinstance(text, str) else None
    text = getattr(block, "text", None)
    return text if isinstance(text, str) else None


def job_description_from(raw: Any) -> str:
    """Pull the readable posting out of a `get_job_details` result.

    The tool answers with MCP content blocks wrapping a JSON document, and the
    posting itself sits at `sections.job_posting`. Stringifying the result
    instead — which is what this replaced — hands the model a Python repr of a
    list of dicts around escaped JSON. It survives that, but two things go wrong:
    the wrapper costs tokens on every posting, and the length cap in the extract
    node then measures the repr rather than the description, so on a long posting
    the requirements are what gets truncated away.

    Args:
        raw: whatever the tool returned.

    Returns:
        The posting text, falling back to the raw text and finally to `str(raw)`
        so a shape we have not seen still reaches the model rather than being
        dropped.
    """
    blocks = raw if isinstance(raw, list) else [raw]
    texts = [text for text in (_block_text(block) for block in blocks) if text]
    if not texts:
        return str(raw)

    joined = "\n".join(texts)
    try:
        document = json.loads(joined)
    except (TypeError, ValueError):
        return joined

    if isinstance(document, dict):
        sections = document.get("sections")
        if isinstance(sections, dict):
            posting = sections.get("job_posting")
            if isinstance(posting, str) and posting.strip():
                return posting
        for key in ("description", "text", "content"):
            value = document.get(key)
            if isinstance(value, str) and value.strip():
                return value

    return joined


def filter_read_only(tools: list[BaseTool]) -> list[BaseTool]:
    """Keep only allowlisted tools and report the rest loudly."""
    allowed: list[BaseTool] = []
    for tool in tools:
        if tool.name in READ_ONLY_TOOLS:
            allowed.append(tool)
        else:
            logger.info("LinkedIn MCP: tool %s is not part of the agent's toolset", tool.name)
    return allowed


async def build_linkedin_tools() -> list[BaseTool]:
    """Return the read-only LinkedIn tools.

    An empty list is a valid result: the agent falls back to the guest source and
    Tavily and must flag the data as incomplete. Raising here is not an option.

    The session check is why this is not simply a connection attempt. The server
    registers and lists all of its tools with no session whatsoever, so a dead
    login produces a full toolset whose every call fails with an authentication
    error buried in the result. That is the failure mode this guards against: a
    run that looks successful and collected nothing.
    """
    global _degradation

    parts = _command_parts()
    if parts is None:
        return _degrade(
            "LinkedIn MCP is not configured (SCOUT_LINKEDIN_MCP_COMMAND is empty), so nothing "
            "in this run came from a LinkedIn account."
        )

    try:
        ensure_safe_command(parts)
    except UnsafeLinkedInCommandError as exc:
        logger.error("%s", exc)
        return _degrade(
            f"LinkedIn MCP was refused for safety and never started: the launch command is "
            f"missing {REQUIRED_LAUNCH_FLAG}, which would let the server adopt the browser's "
            f"real LinkedIn session. Fix SCOUT_LINKEDIN_MCP_COMMAND in .env."
        )

    health = await linkedin_health(parts)
    if not health.authenticated:
        return _degrade(
            f"LinkedIn MCP has no usable session ({health.detail}), so nothing in this run came "
            f"from a LinkedIn account. Restore it by running `{parts[0]} --login` once in a "
            f"terminal, signed in to the burner account."
        )

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        # `env` is deliberately left out: the MCP stdio client then forwards its
        # default subset (HOME, PATH, USER, SHELL, TERM, LOGNAME), and HOME is
        # what points the server at the stored profile in ~/.linkedin-mcp/.
        client = MultiServerMCPClient(
            {
                "linkedin": {
                    "transport": "stdio",
                    "command": parts[0],
                    "args": parts[1:],
                }
            }
        )
        tools = await client.get_tools()
    except Exception as exc:
        return _degrade(f"LinkedIn MCP failed to start ({exc}), so no LinkedIn data was collected.")

    _degradation = None
    return filter_read_only(list(tools))
