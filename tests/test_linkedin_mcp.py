"""The `--status` session probe and the command it is built from.

The probe runs a real subprocess against stub shell scripts rather than the
LinkedIn server. Exit codes, a hanging child and a missing binary are the three
things it has to get right, and none of them are worth testing through a mock.
Nothing here touches the network or a LinkedIn session.

The stubs reproduce the output of mcp-server-linkedin 4.23.3 verbatim: it writes
to stdout, leaves stderr empty, exits 0 on a valid session and 1 on every other
outcome.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scout.tools import linkedin_mcp
from scout.tools.linkedin_mcp import (
    REQUIRED_LAUNCH_FLAG,
    LinkedInHealth,
    build_status_command,
    linkedin_health,
    probe_session,
    reset_linkedin_health,
)

PROFILE_DIR = "/home/u/.linkedin-mcp/profile"
VALID_OUTPUT = f"✅ Session is valid (profile: {PROFILE_DIR})"
NO_SESSION_OUTPUT = f"❌ No valid source session found at {PROFILE_DIR}"
EXPIRED_OUTPUT = f"❌ Session expired or invalid (profile: {PROFILE_DIR})"
UNVERIFIED_OUTPUT = "ℹ️ Source cookie validity is not verified in this mode"

# Once a profile exists the command describes it before saying anything about the
# session, so the verdict is never the first line. Only the no-profile case is
# a single line, which is why stubs modelled on it hid this for a while.
STATUS_HEADER = (
    "Current runtime: macos-arm64-host\n"
    "Source runtime: macos-arm64-host\n"
    "Login generation: 866f5bdc-2424-42ee-bcbc-c03b3f362203\n"
    f"Profile mode: source ({PROFILE_DIR})"
)


def _stub(tmp_path: Path, body: str) -> str:
    """Write an executable stand-in for the server binary and return its path."""
    script = tmp_path / "mcp-server-linkedin"
    script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    script.chmod(0o755)
    return str(script)


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_linkedin_health()
    yield
    reset_linkedin_health()


class TestStatusCommand:
    def test_probe_asks_for_status_and_keeps_auto_import_off(self):
        """`--status` opens the browser too, so the safety flag has to come along."""
        command = build_status_command(
            ["/bin/mcp-server-linkedin", "--transport", "stdio", REQUIRED_LAUNCH_FLAG]
        )
        assert command[0] == "/bin/mcp-server-linkedin"
        assert "--status" in command
        assert REQUIRED_LAUNCH_FLAG in command

    def test_runtime_flags_are_dropped(self):
        """Transport and timeouts mean nothing to a one-shot check."""
        command = build_status_command(
            [
                "/bin/mcp-server-linkedin",
                "--transport",
                "stdio",
                "--log-level",
                "ERROR",
                "--tool-timeout",
                "300",
                REQUIRED_LAUNCH_FLAG,
            ]
        )
        assert "--transport" not in command
        assert "--tool-timeout" not in command

    def test_profile_directory_is_carried_over(self):
        """Checking a different profile than the server will use answers nothing."""
        command = build_status_command(
            ["/bin/mcp-server-linkedin", "--user-data-dir", PROFILE_DIR, REQUIRED_LAUNCH_FLAG]
        )
        assert command[-2:] == ["--user-data-dir", PROFILE_DIR]

    def test_profile_directory_in_equals_form_is_carried_over(self):
        command = build_status_command(
            ["/bin/mcp-server-linkedin", f"--user-data-dir={PROFILE_DIR}", REQUIRED_LAUNCH_FLAG]
        )
        assert f"--user-data-dir={PROFILE_DIR}" in command

    def test_a_dangling_value_flag_does_not_crash(self):
        command = build_status_command(["/bin/mcp-server-linkedin", "--user-data-dir"])
        assert command[0] == "/bin/mcp-server-linkedin"


class TestProbe:
    async def test_exit_zero_means_a_usable_session(self, tmp_path):
        binary = _stub(tmp_path, f'echo "{VALID_OUTPUT}"\nexit 0')
        health = await probe_session([binary], timeout_seconds=10)
        assert health.authenticated
        assert "Session is valid" in health.detail

    @pytest.mark.parametrize("output", [NO_SESSION_OUTPUT, EXPIRED_OUTPUT])
    async def test_exit_one_means_no_usable_session(self, tmp_path, output):
        binary = _stub(tmp_path, f'echo "{output}"\nexit 1')
        health = await probe_session([binary], timeout_seconds=10)
        assert not health.authenticated
        assert health.detail == output

    async def test_the_servers_own_wording_is_kept_for_the_user(self, tmp_path):
        """The reason has to survive to the report, not be flattened to a boolean."""
        binary = _stub(
            tmp_path,
            f'echo "{NO_SESSION_OUTPUT}"\necho "   Run with --login to create a source session"'
            "\nexit 1",
        )
        health = await probe_session([binary], timeout_seconds=10)
        assert "No valid source session found" in health.detail

    async def test_the_verdict_survives_the_status_header(self, tmp_path):
        """An expired session prints the profile header first; the reason is below it.

        This is the case the user is most likely to hit, and reporting
        `Current runtime: …` back as the reason would tell them nothing.
        """
        binary = _stub(tmp_path, f'echo "{STATUS_HEADER}\n{EXPIRED_OUTPUT}"\nexit 1')
        health = await probe_session([binary], timeout_seconds=10)
        assert not health.authenticated
        assert health.detail == EXPIRED_OUTPUT
        assert "Current runtime" not in health.detail

    async def test_a_valid_session_reports_the_verdict_not_the_header(self, tmp_path):
        binary = _stub(tmp_path, f'echo "{STATUS_HEADER}\n{VALID_OUTPUT}"\nexit 0')
        health = await probe_session([binary], timeout_seconds=10)
        assert health.authenticated
        assert health.detail == VALID_OUTPUT

    async def test_the_unverified_foreign_runtime_note_is_surfaced(self, tmp_path):
        """The server admits it did not check the cookie here, and exits 0 anyway.

        We still trust the exit code, but the caveat has to reach the log rather
        than be replaced by a runtime name.
        """
        binary = _stub(tmp_path, f'echo "{STATUS_HEADER}\n{UNVERIFIED_OUTPUT}"\nexit 0')
        health = await probe_session([binary], timeout_seconds=10)
        assert health.authenticated
        assert health.detail == UNVERIFIED_OUTPUT

    async def test_unmarked_output_falls_back_to_the_last_line(self, tmp_path):
        """No marker to find, so guess at the end rather than the header."""
        binary = _stub(tmp_path, 'echo "Current runtime: macos-arm64-host\nsomething odd"\nexit 1')
        health = await probe_session([binary], timeout_seconds=10)
        assert health.detail == "something odd"

    async def test_output_on_stderr_is_not_lost(self, tmp_path):
        binary = _stub(tmp_path, 'echo "boom" >&2\nexit 1')
        health = await probe_session([binary], timeout_seconds=10)
        assert not health.authenticated
        assert "boom" in health.detail

    async def test_silent_failure_still_reports_the_exit_code(self, tmp_path):
        binary = _stub(tmp_path, "exit 3")
        health = await probe_session([binary], timeout_seconds=10)
        assert not health.authenticated
        assert "3" in health.detail

    async def test_a_hanging_probe_is_killed_not_awaited(self, tmp_path):
        """A session check must never be able to stall a run."""
        binary = _stub(tmp_path, "sleep 30")
        health = await probe_session([binary], timeout_seconds=0.3)
        assert not health.authenticated
        assert "no answer" in health.detail

    async def test_a_missing_binary_is_not_an_exception(self, tmp_path):
        health = await probe_session([str(tmp_path / "absent")], timeout_seconds=10)
        assert not health.authenticated
        assert "could not run" in health.detail

    async def test_a_binary_that_is_not_executable_is_not_an_exception(self, tmp_path):
        script = tmp_path / "mcp-server-linkedin"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o644)
        health = await probe_session([str(script)], timeout_seconds=10)
        assert not health.authenticated


class TestHealthCache:
    async def test_the_probe_runs_once_per_process(self, monkeypatch):
        """Three call sites want this answer; one headless browser launch is enough."""
        calls = 0

        async def counting(parts, timeout_seconds=linkedin_mcp.STATUS_TIMEOUT_SECONDS):
            nonlocal calls
            calls += 1
            return LinkedInHealth(True, VALID_OUTPUT)

        monkeypatch.setattr(linkedin_mcp, "probe_session", counting)
        parts = ["/bin/mcp-server-linkedin", REQUIRED_LAUNCH_FLAG]
        assert (await linkedin_health(parts)).authenticated
        await linkedin_health(parts)
        await linkedin_health(parts)
        assert calls == 1

    async def test_refresh_probes_again(self, monkeypatch):
        calls = 0

        async def counting(parts, timeout_seconds=linkedin_mcp.STATUS_TIMEOUT_SECONDS):
            nonlocal calls
            calls += 1
            return LinkedInHealth(False, EXPIRED_OUTPUT)

        monkeypatch.setattr(linkedin_mcp, "probe_session", counting)
        parts = ["/bin/mcp-server-linkedin", REQUIRED_LAUNCH_FLAG]
        await linkedin_health(parts)
        await linkedin_health(parts, refresh=True)
        assert calls == 2
