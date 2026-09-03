"""A ceiling on the cost of a single run.

Counts tokens from the actual response metadata and ends the run gracefully when
the budget is spent: the agent gets a chance to answer with whatever it has
already gathered instead of dying halfway.

The counter lives in graph state rather than on the middleware object, otherwise
a "per run" limit quietly becomes a limit for the lifetime of the process.
"""

from __future__ import annotations

import logging
from typing import Any, NotRequired

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
    hook_config,
)
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..config import BudgetsConfig, get_config

logger = logging.getLogger(__name__)


class CostGuardState(AgentState):
    """Agent state extended with a cumulative token counter."""

    scout_tokens_used: NotRequired[int]


class CostGuardMiddleware(AgentMiddleware[CostGuardState, Any]):
    """Stop the run once the token budget is exhausted."""

    state_schema = CostGuardState

    def __init__(self, budgets: BudgetsConfig | None = None) -> None:
        super().__init__()
        self.budgets = budgets or get_config().budgets

    @property
    def name(self) -> str:
        """Middleware name as it appears in traces."""
        return "CostGuardMiddleware"

    @hook_config(can_jump_to=["end"])
    def before_model(
        self,
        state: CostGuardState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """End the run before another model call if the budget is already spent."""
        used = state.get("scout_tokens_used", 0) or 0
        if used < self.budgets.max_tokens_per_run:
            return None

        logger.warning("Token budget exhausted: %s", used)
        return {
            "jump_to": "end",
            "messages": [
                AIMessage(
                    content=(
                        f"Stopping on the token budget ({used:,} of "
                        f"{self.budgets.max_tokens_per_run:,}). Everything gathered so far "
                        "is above. Tell me what to continue with and I will take it in a "
                        "separate pass, which is cheaper than one enormous run."
                    )
                )
            ],
        }

    def after_model(
        self,
        state: CostGuardState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """Accumulate token usage reported by the last model response."""
        messages = state.get("messages") or []
        if not messages:
            return None
        last = messages[-1]
        usage = getattr(last, "usage_metadata", None)
        if not usage:
            return None
        total = usage.get("total_tokens") or 0
        if not total:
            return None
        return {"scout_tokens_used": (state.get("scout_tokens_used", 0) or 0) + total}


def build_cost_middleware(budgets: BudgetsConfig | None = None) -> list[Any]:
    """Return the full set of cost limiters.

    The stock `ToolCallLimitMiddleware` and `ModelCallLimitMiddleware` cover call
    counts; the local `CostGuardMiddleware` adds what they lack, which is token
    accounting.
    """
    cfg = budgets or get_config().budgets
    return [
        CostGuardMiddleware(cfg),
        ToolCallLimitMiddleware(run_limit=cfg.max_tool_calls_per_run, exit_behavior="end"),
        ModelCallLimitMiddleware(run_limit=60, exit_behavior="end"),
    ]
