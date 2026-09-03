"""The LinkedIn call budget: the main protection for the burner account.

Three mechanisms: a hard ceiling per run and per hour, jitter between requests,
and exponential backoff on 429.

The key behaviour: when the budget runs out the tool returns a clear textual
refusal to the agent rather than raising. The agent is expected to carry on with
other sources and flag the gap honestly instead of dying mid-conversation.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage

from ..config import BudgetsConfig, get_config
from ..tools.linkedin_mcp import READ_ONLY_TOOLS

logger = logging.getLogger(__name__)

_REFUSAL = (
    "The LinkedIn call budget for this run is exhausted ({used}/{limit}). "
    "This is account protection, not a failure. Continue with the guest job "
    "source and web search, and tell the user that this part of the data is "
    "incomplete."
)

_HOURLY_REFUSAL = (
    "Hourly LinkedIn call limit reached ({used}/{limit}). Continue on the other "
    "sources and warn the user that the data is incomplete."
)

_RATE_LIMITED = (
    "LinkedIn is still rate limiting after a retry. Switch to the guest job "
    "source and web search, and mark the data as incomplete."
)


class LinkedInBudgetMiddleware(AgentMiddleware):
    """Count LinkedIn tool calls and slow them down.

    The per-run counter lives on the middleware instance, so an instance belongs
    to one agent build and must not be shared across independent processes.
    """

    def __init__(self, budgets: BudgetsConfig | None = None) -> None:
        super().__init__()
        self.budgets = budgets or get_config().budgets
        self._run_calls = 0
        self._hour_window: deque[float] = deque()
        self._last_call_at: float | None = None

    @property
    def name(self) -> str:
        """Middleware name as it appears in traces."""
        return "LinkedInBudgetMiddleware"

    def _prune_hour_window(self, now: float) -> None:
        while self._hour_window and now - self._hour_window[0] > 3600:
            self._hour_window.popleft()

    def _refusal_reason(self) -> str | None:
        """Return the refusal text when a limit is hit, or None when a call is allowed."""
        now = time.monotonic()
        self._prune_hour_window(now)

        if self._run_calls >= self.budgets.linkedin_calls_per_run:
            return _REFUSAL.format(used=self._run_calls, limit=self.budgets.linkedin_calls_per_run)
        if len(self._hour_window) >= self.budgets.linkedin_calls_per_hour:
            return _HOURLY_REFUSAL.format(
                used=len(self._hour_window), limit=self.budgets.linkedin_calls_per_hour
            )
        return None

    def _register_call(self) -> None:
        now = time.monotonic()
        self._run_calls += 1
        self._hour_window.append(now)
        self._last_call_at = now

    def _delay_needed(self) -> float:
        """Return how long to wait before the next request, with jitter."""
        target = random.uniform(  # noqa: S311 - jitter, not cryptography
            self.budgets.linkedin_min_delay_seconds,
            self.budgets.linkedin_max_delay_seconds,
        )
        if self._last_call_at is None:
            return 0.0
        elapsed = time.monotonic() - self._last_call_at
        return max(0.0, target - elapsed)

    @staticmethod
    def _is_rate_limited(result: Any) -> bool:
        """Detect a rate-limit response by inspecting the tool message text."""
        text = getattr(result, "content", None)
        if not isinstance(text, str):
            return False
        lowered = text.lower()
        return "429" in lowered or "rate limit" in lowered or "too many requests" in lowered

    def reset_run(self) -> None:
        """Clear the per-run counter, keeping the hourly window intact."""
        self._run_calls = 0

    async def awrap_tool_call(self, request: ToolCallRequest, handler: Any) -> Any:
        """Apply the budget, jitter and backoff around an async LinkedIn call."""
        name = request.tool_call.get("name", "")
        if name not in READ_ONLY_TOOLS:
            return await handler(request)

        reason = self._refusal_reason()
        if reason is not None:
            logger.info("LinkedIn budget: refusing %s", name)
            return ToolMessage(content=reason, tool_call_id=request.tool_call["id"])

        delay = self._delay_needed()
        if delay > 0:
            await asyncio.sleep(delay)

        self._register_call()
        result = await handler(request)

        # Back off and retry once: a 429 usually clears after a pause, but a
        # second one in a row is a signal to stop rather than keep hammering.
        if self._is_rate_limited(result):
            logger.warning("LinkedIn returned 429 for %s, backing off", name)
            await asyncio.sleep(random.uniform(20, 40))  # noqa: S311
            if self._refusal_reason() is None:
                self._register_call()
                result = await handler(request)
            if self._is_rate_limited(result):
                return ToolMessage(content=_RATE_LIMITED, tool_call_id=request.tool_call["id"])
        return result

    def wrap_tool_call(self, request: ToolCallRequest, handler: Any) -> Any:
        """Synchronous path. MCP tools are async, but this keeps the guard total."""
        name = request.tool_call.get("name", "")
        if name not in READ_ONLY_TOOLS:
            return handler(request)

        reason = self._refusal_reason()
        if reason is not None:
            return ToolMessage(content=reason, tool_call_id=request.tool_call["id"])

        delay = self._delay_needed()
        if delay > 0:
            time.sleep(delay)

        self._register_call()
        return handler(request)
