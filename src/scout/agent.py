"""Agent assembly.

The hybrid from the design: a Deep Agent orchestrator runs the conversation and
delegates the work, while data collection lives in a deterministic subgraph that
the agent sees as the single `research_jobs` tool.

The toolset is put together with an eye on what must NOT be in it: there is no
ability to message people on LinkedIn — not hidden behind a confirmation, simply
absent (see tools/linkedin_mcp.py).
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from deepagents import FilesystemMiddleware, FilesystemPermission, create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import SummarizationMiddleware, TodoListMiddleware
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from .config import REPO_ROOT, get_config, get_settings
from .graphs.research import research_jobs
from .memory import load_taxonomy
from .middleware.cost_guard import build_cost_middleware
from .middleware.injection_guard import InjectionGuardMiddleware
from .middleware.linkedin_budget import LinkedInBudgetMiddleware
from .middleware.pii import build_pii_middleware
from .models import chat_model
from .prompts import (
    COMPANY_RESEARCHER_PROMPT,
    CV_WRITER_PROMPT,
    JOB_ANALYST_PROMPT,
    build_system_prompt,
)
from .tools.analysis import (
    gap_analysis,
    list_known_jobs,
    read_candidate_profile,
    read_job_dossier,
    remember_preference,
    score_jobs,
)
from .tools.profile_ingest import bootstrap_profile
from .tools.render_pdf import render_pdf
from .tools.tavily import build_tavily_tools

logger = logging.getLogger(__name__)

SKILLS_DIR = str(REPO_ROOT / "skills")

# Filesystem tools without `execute`. Running arbitrary commands is not needed
# for any of the agent's tasks, and the cost of a mistake dwarfs the convenience.
FsTool = Literal["ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute"]
FS_TOOLS: list[FsTool] = ["ls", "read_file", "write_file", "edit_file", "glob", "grep"]

# A guest run may look but not touch. Reading stays because skills are files and
# the agent loses its own reference material without it.
FS_TOOLS_READONLY: list[FsTool] = ["ls", "read_file", "glob", "grep"]

# data/private is the only place holding the real email and phone number. The
# model must not see them: they are substituted while rendering the PDF, outside
# the context. Without this denial, the PII middleware would protect against
# everything except a direct file read, which the agent would work out on its own.
# Rule paths are always absolute — FilesystemPermission requires it.
PRIVATE_PATHS = [
    str(REPO_ROOT / "data" / "private" / "**"),
    str(REPO_ROOT / "data" / "private"),
]

# The filesystem backend is rooted at the repository, and the repository root is
# where `.env` lives. Denying only data/private left every key in the project —
# OpenAI, Tavily, LangSmith, the database URL — one `read_file` call away, and
# the agent reads hostile text by design: a vacancy description that talks it
# into opening .env and quoting the result is the whole attack. The git
# directory goes too; it carries the remote URL and any credentials in it.
SECRET_PATHS = [
    str(REPO_ROOT / ".env"),
    str(REPO_ROOT / ".env.*"),
    str(REPO_ROOT / ".git"),
    str(REPO_ROOT / ".git" / "**"),
]

# The CV skills are read by cv-writer, not by the orchestrator: they are long and
# there is no reason to hold them in the main context. Skills are not inherited,
# so they are passed explicitly.
CV_SKILLS = [SKILLS_DIR]


def build_private_deny() -> list[FilesystemPermission]:
    """Deny rules for private data and secrets, shared by the orchestrator and subagents."""
    return [
        FilesystemPermission(
            operations=["read", "write"],
            paths=[*PRIVATE_PATHS, *SECRET_PATHS],
            mode="deny",
        )
    ]


def build_filesystem_middleware(
    backend: FilesystemBackend,
    permissions: list[FilesystemPermission],
    *,
    tools: list[FsTool] | None = None,
) -> FilesystemMiddleware:
    """Filesystem middleware carrying the restricted toolset and the private-data denial.

    A fresh instance per agent. The harness builds its own unrestricted
    `FilesystemMiddleware` for every declarative subagent, and the supported way
    to override it is to put an instance of the same middleware into the
    subagent's own `middleware` list: entries there replace base-stack middleware
    of the same name. Without this, subagents would keep the full default
    toolset, including `delete`.
    """
    return FilesystemMiddleware(
        backend=backend, tools=tools or FS_TOOLS, _permissions=permissions
    )


async def build_tools(*, guest: bool = False) -> tuple[list[BaseTool], list[BaseTool]]:
    """Return (orchestrator tools, read-only LinkedIn tools).

    A guest gets neither LinkedIn nor anything that writes. The LinkedIn refusal
    is not about the data — the guest source is public anyway — but about the
    account: the burner session is a finite, bannable resource belonging to the
    owner, and a stranger on a web page must not be able to spend it.
    """
    from .tools.linkedin_mcp import build_linkedin_tools

    linkedin: list[BaseTool] = [] if guest else await build_linkedin_tools()
    tavily = build_tavily_tools()

    orchestrator: list[BaseTool] = [
        research_jobs,
        list_known_jobs,
        score_jobs,
        gap_analysis,
        *tavily,
    ]
    if not guest:
        # Both write to the owner's memory: one stores preferences, the other
        # reads the CV out of data/private and rewrites the Candidate Profile.
        orchestrator.extend([remember_preference, bootstrap_profile])

    return orchestrator, linkedin


def build_subagents(
    linkedin: list[BaseTool],
    tavily: list[BaseTool],
    *,
    backend: FilesystemBackend,
    permissions: list[FilesystemPermission],
    guest: bool = False,
) -> list[Any]:
    """Subagents with isolated context.

    Each returns only its conclusion upstream: full vacancy descriptions and long
    skill texts stay inside and never reach the main conversation.

    `backend` and `permissions` are threaded in so every subagent gets the same
    restricted filesystem middleware as the orchestrator instead of the
    unrestricted one the harness would otherwise build for it.
    """
    settings = get_settings()
    fs_tools: list[FsTool] = FS_TOOLS_READONLY if guest else FS_TOOLS

    def filesystem() -> FilesystemMiddleware:
        return build_filesystem_middleware(backend, permissions, tools=fs_tools)

    subagents: list[Any] = [
        {
            "name": "job-analyst",
            "description": (
                "Deep analysis of one vacancy by its id. Returns the mandatory "
                "requirements, hidden signals and a conclusion. Call it per vacancy."
            ),
            "system_prompt": JOB_ANALYST_PROMPT,
            "tools": [read_job_dossier, *linkedin, *tavily],
            "model": chat_model(settings.scout_model_fast),
            "middleware": [filesystem()],
            "permissions": permissions,
        },
        {
            "name": "cv-writer",
            "description": (
                "Writes a CV for a specific vacancy and text for the LinkedIn profile. "
                "Pass it the vacancy id and what you need produced."
            ),
            "system_prompt": CV_WRITER_PROMPT,
            # The profile tool goes to cv-writer alone: it is the only subagent
            # whose prompt forbids writing anything the profile does not contain,
            # and it was the only one with no way to check.
            "tools": [read_job_dossier, read_candidate_profile, render_pdf],
            "skills": CV_SKILLS,
            "model": chat_model(settings.scout_model_smart),
            "middleware": [filesystem()],
            "permissions": permissions,
        },
        {
            "name": "company-researcher",
            "description": "Gathers context on a company: stack, size, process, reputation.",
            "system_prompt": COMPANY_RESEARCHER_PROMPT,
            "tools": [
                *tavily,
                *[
                    t
                    for t in linkedin
                    if t.name in {"get_company_profile", "get_company_employees"}
                ],
            ],
            "model": chat_model(settings.scout_model_fast),
            "middleware": [filesystem()],
            "permissions": permissions,
        },
    ]

    if guest:
        # cv-writer is the one subagent holding read_candidate_profile and
        # render_pdf, so it is the one that reaches the owner's CV and their real
        # contacts. A guest has no profile to write from in any case.
        subagents = [s for s in subagents if s["name"] != "cv-writer"]

    return subagents


async def build_agent(
    store: BaseStore | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    *,
    guest: bool = False,
):
    """Assemble the agent.

    `store` and `checkpointer` are left empty under `langgraph dev`: the platform
    supplies its own. For local runs, main.py passes them in.

    `guest` builds the restricted agent served to visitors of the personal page.
    The restriction is structural rather than instructed: a capability the guest
    agent was never given cannot be talked into existence by a clever prompt,
    which is the only guarantee worth having on a public endpoint.
    """
    settings = get_settings()
    config = get_config()

    orchestrator_tools, linkedin = await build_tools(guest=guest)
    tavily = build_tavily_tools()

    taxonomy = None
    if store is not None:
        try:
            taxonomy = await load_taxonomy(store)
        except Exception as exc:
            logger.info("Taxonomy unavailable (%s); prompt built without it", exc)

    backend = FilesystemBackend(root_dir=str(REPO_ROOT), virtual_mode=False)
    private_deny = build_private_deny()

    middleware: list[Any] = [
        TodoListMiddleware(),
        # A custom FilesystemMiddleware instead of the built-in one is the only
        # way to withhold `execute` from the agent.
        build_filesystem_middleware(
            backend, private_deny, tools=FS_TOOLS_READONLY if guest else FS_TOOLS
        ),
        LinkedInBudgetMiddleware(config.budgets),
        InjectionGuardMiddleware(),
        *build_pii_middleware(),
        *build_cost_middleware(config.budgets),
        SummarizationMiddleware(
            # Tagged out of the token stream. This model writes a summary of the
            # conversation so far, which is bookkeeping, not an answer; without
            # the tag it would be typed into the user's chat window the moment
            # the context crosses the trigger.
            model=chat_model(settings.scout_model_fast, tags=["langsmith:nostream"]),
            trigger=("fraction", 0.75),
            keep=("messages", 20),
        ),
    ]

    return create_deep_agent(
        name="agentic-sdlc-scout",
        model=chat_model(settings.scout_model_smart),
        system_prompt=build_system_prompt(taxonomy, config, guest=guest),
        tools=orchestrator_tools,
        subagents=build_subagents(
            linkedin, tavily, backend=backend, permissions=private_deny, guest=guest
        ),
        middleware=middleware,
        backend=backend,
        permissions=private_deny,
        skills=[SKILLS_DIR],
        store=store,
        checkpointer=checkpointer,
    )
