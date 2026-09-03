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
from .prompts import (
    COMPANY_RESEARCHER_PROMPT,
    CV_WRITER_PROMPT,
    JOB_ANALYST_PROMPT,
    build_system_prompt,
)
from .tools.analysis import gap_analysis, remember_preference, score_jobs
from .tools.profile_ingest import bootstrap_profile
from .tools.render_pdf import render_pdf
from .tools.tavily import build_tavily_tools

logger = logging.getLogger(__name__)

SKILLS_DIR = str(REPO_ROOT / "skills")

# Filesystem tools without `execute`. Running arbitrary commands is not needed
# for any of the agent's tasks, and the cost of a mistake dwarfs the convenience.
FsTool = Literal["ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute"]
FS_TOOLS: list[FsTool] = ["ls", "read_file", "write_file", "edit_file", "glob", "grep"]

# data/private is the only place holding the real email and phone number. The
# model must not see them: they are substituted while rendering the PDF, outside
# the context. Without this denial, the PII middleware would protect against
# everything except a direct file read, which the agent would work out on its own.
# Rule paths are always absolute — FilesystemPermission requires it.
PRIVATE_PATHS = [
    str(REPO_ROOT / "data" / "private" / "**"),
    str(REPO_ROOT / "data" / "private"),
]

# The CV skills are read by cv-writer, not by the orchestrator: they are long and
# there is no reason to hold them in the main context. Skills are not inherited,
# so they are passed explicitly.
CV_SKILLS = [SKILLS_DIR]


async def build_tools() -> tuple[list[BaseTool], list[BaseTool]]:
    """Return (orchestrator tools, read-only LinkedIn tools)."""
    from .tools.linkedin_mcp import build_linkedin_tools

    linkedin = await build_linkedin_tools()
    tavily = build_tavily_tools()

    orchestrator: list[BaseTool] = [
        research_jobs,
        score_jobs,
        gap_analysis,
        remember_preference,
        bootstrap_profile,
        *tavily,
    ]
    return orchestrator, linkedin


def build_subagents(linkedin: list[BaseTool], tavily: list[BaseTool]) -> list[Any]:
    """Subagents with isolated context.

    Each returns only its conclusion upstream: full vacancy descriptions and long
    skill texts stay inside and never reach the main conversation.
    """
    settings = get_settings()
    return [
        {
            "name": "job-analyst",
            "description": (
                "Deep analysis of one vacancy by its id. Returns the mandatory "
                "requirements, hidden signals and a conclusion. Call it per vacancy."
            ),
            "system_prompt": JOB_ANALYST_PROMPT,
            "tools": [*linkedin, *tavily],
            "model": settings.scout_model_fast,
        },
        {
            "name": "cv-writer",
            "description": (
                "Writes a CV for a specific vacancy and text for the LinkedIn profile. "
                "Pass it the vacancy id and what you need produced."
            ),
            "system_prompt": CV_WRITER_PROMPT,
            "tools": [render_pdf],
            "skills": CV_SKILLS,
            "model": settings.scout_model_smart,
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
            "model": settings.scout_model_fast,
        },
    ]


async def build_agent(
    store: BaseStore | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Assemble the agent.

    `store` and `checkpointer` are left empty under `langgraph dev`: the platform
    supplies its own. For local runs, main.py passes them in.
    """
    settings = get_settings()
    config = get_config()

    orchestrator_tools, linkedin = await build_tools()
    tavily = build_tavily_tools()

    taxonomy = None
    if store is not None:
        try:
            taxonomy = await load_taxonomy(store)
        except Exception as exc:
            logger.info("Taxonomy unavailable (%s); prompt built without it", exc)

    backend = FilesystemBackend(root_dir=str(REPO_ROOT), virtual_mode=False)
    private_deny = [
        FilesystemPermission(operations=["read", "write"], paths=PRIVATE_PATHS, mode="deny")
    ]

    middleware: list[Any] = [
        TodoListMiddleware(),
        # A custom FilesystemMiddleware instead of the built-in one is the only
        # way to withhold `execute` from the agent.
        FilesystemMiddleware(backend=backend, tools=FS_TOOLS, _permissions=private_deny),
        LinkedInBudgetMiddleware(config.budgets),
        InjectionGuardMiddleware(),
        *build_pii_middleware(),
        *build_cost_middleware(config.budgets),
        SummarizationMiddleware(
            model=settings.scout_model_fast,
            trigger=("fraction", 0.75),
            keep=("messages", 20),
        ),
    ]

    return create_deep_agent(
        name="agentic-sdlc-scout",
        model=settings.scout_model_smart,
        system_prompt=build_system_prompt(taxonomy, config),
        tools=orchestrator_tools,
        subagents=build_subagents(linkedin, tavily),
        middleware=middleware,
        backend=backend,
        permissions=private_deny,
        skills=[SKILLS_DIR],
        store=store,
        checkpointer=checkpointer,
    )
