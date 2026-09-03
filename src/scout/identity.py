"""Whose run this is.

Phase 1 had one user, so the answer was a constant in the settings and every
call site read it from there. That is exactly the wrong shape for phase 3. The
moment the agent answers an HTTP request, `user_id` stops being a property of
the process and becomes a property of the request, and a process-wide constant
serving many callers is not a small inaccuracy — it is one shared memory
namespace. The first visitor to the personal page would read the owner's
Candidate Profile, contacts and all.

So identity travels the same way the store does: through the ambient LangGraph
run context, which is per-invocation. The fallback to settings keeps the CLI and
the tests working unchanged, where there really is only one user.

The guest flag rides along because the two facts are inseparable in practice.
Knowing *who* is asking is only half of it; the other half is what they are
allowed to do, and every place that cares about one cares about the other.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import get_settings


@dataclass(frozen=True)
class Identity:
    """The caller a run acts for."""

    user_id: str
    is_guest: bool = False

    @property
    def may_read_owner_profile(self) -> bool:
        """Whether the Candidate Profile and its contacts are in reach.

        Only the owner's own runs may see it. It holds the CV verbatim: names,
        employers, and the evidence lines the rubric scores against.
        """
        return not self.is_guest

    @property
    def may_write(self) -> bool:
        """Whether the run may modify anything that outlives it.

        Guests get a read-only agent. They can search and be told about
        vacancies; they cannot rewrite the owner's profile, stored feedback or
        rendered documents.
        """
        return not self.is_guest


OWNER_FALLBACK = Identity(user_id="owner", is_guest=False)


def current_identity() -> Identity:
    """The identity of the run in progress.

    Reads the ambient LangGraph config, which is populated per invocation from
    `config={"configurable": {...}}`. Outside a run — in the CLI, in tests, in a
    direct tool call — there is no ambient config and the configured single user
    is the honest answer.
    """
    configurable = _configurable()
    user_id = configurable.get("user_id")
    if not user_id:
        settings = get_settings()
        return Identity(user_id=settings.scout_user_id, is_guest=False)
    return Identity(user_id=str(user_id), is_guest=bool(configurable.get("is_guest", False)))


def current_user_id() -> str:
    """Shorthand for the namespace key, which is what most call sites want."""
    return current_identity().user_id


def run_context(identity: Identity) -> dict[str, object]:
    """The `configurable` payload that carries an identity into a run."""
    return {"user_id": identity.user_id, "is_guest": identity.is_guest}


def _configurable() -> dict:
    try:
        from langgraph.config import get_config as get_run_config

        return (get_run_config() or {}).get("configurable") or {}
    except Exception:
        # No ambient run: get_config raises outside a graph invocation, and that
        # is the ordinary case for the CLI and the unit tests.
        return {}
