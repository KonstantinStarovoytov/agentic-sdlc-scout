"""Long-term memory and checkpoints.

Postgres on Neon when `SCOUT_DATABASE_URL` is set, in-memory when it is not.
The second mode is not a test stub but a working development path: the agent
has to start and do something before an external service exists.

Neon's free tier suspends the compute, so the pool is configured for reconnects
with generous timeouts from the outset. Otherwise the first query of the day
looks like a breakage.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "openai:text-embedding-3-small"
EMBEDDING_DIMS = 1536


def profile_ns(user_id: str) -> tuple[str, ...]:
    """Candidate Profile: the source of truth about the user."""
    return ("profile", user_id)


def jobs_ns(user_id: str) -> tuple[str, ...]:
    """Job dossiers keyed by canonical id. The basis of dedup."""
    return ("jobs", user_id)


def companies_ns() -> tuple[str, ...]:
    """Company research cache, shared across users."""
    return ("companies",)


def artifacts_ns(user_id: str) -> tuple[str, ...]:
    """Generated CVs, letters and LinkedIn copy."""
    return ("artifacts", user_id)


def taxonomy_ns() -> tuple[str, ...]:
    """The living record of what the track demands."""
    return ("taxonomy",)


def feedback_ns(user_id: str) -> tuple[str, ...]:
    """User reactions: "too senior", "not this company".

    Feeds the prefilter and scoring on later runs. Without it the agent brings
    back the same junk every time.
    """
    return ("feedback", user_id)


def _index_config(settings: Settings) -> Any | None:
    """Enable semantic search only when an OpenAI key is present.

    The model is built here rather than named. Passing the name would leave the
    store to resolve it, and that resolution reads the environment — so a key
    held only in `.env` would fail, the store would fall back to in-memory, and
    the run would continue without persisting anything.
    """
    if not settings.openai_api_key:
        logger.info("OPENAI_API_KEY is not set: memory runs without semantic search")
        return None
    from .models import embeddings_model

    return {"dims": EMBEDDING_DIMS, "embed": embeddings_model(EMBEDDING_MODEL), "fields": ["$"]}


# Neon takes seconds to wake, so the timeouts are well above the defaults.
_POOL_CONFIG: Any = {"min_size": 1, "max_size": 5, "timeout": 30.0}


@contextlib.asynccontextmanager
async def open_memory(
    settings: Settings | None = None,
) -> AsyncIterator[tuple[BaseStore, BaseCheckpointSaver]]:
    """Yield a ready store and checkpointer.

    If Postgres is unreachable this falls back to in-memory and says so in the
    log: partial capability beats failing to start at all.
    """
    cfg = settings or get_settings()

    if not cfg.has_postgres:
        logger.info("SCOUT_DATABASE_URL is not set: memory is in-process and will not persist")
        async with _open_in_memory() as pair:
            yield pair
        return

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.store.postgres.aio import AsyncPostgresStore

    url = cfg.scout_database_url or ""
    try:
        async with (
            AsyncPostgresStore.from_conn_string(
                url, index=_index_config(cfg), pool_config=_POOL_CONFIG
            ) as store,
            AsyncPostgresSaver.from_conn_string(url) as saver,
        ):
            await store.setup()
            await saver.setup()
            yield store, saver
    except Exception as exc:
        logger.warning("Postgres is unavailable (%s): falling back to in-memory", exc)
        async with _open_in_memory() as pair:
            yield pair


@contextlib.asynccontextmanager
async def _open_in_memory() -> AsyncIterator[tuple[BaseStore, BaseCheckpointSaver]]:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    yield InMemoryStore(), InMemorySaver()


async def put_job(store: BaseStore, user_id: str, job: Any) -> None:
    """Store a full dossier. Only the card ever reaches the agent's context."""
    await store.aput(jobs_ns(user_id), job.canonical_id, job.model_dump(mode="json"))


async def get_known_job_ids(store: BaseStore, user_id: str) -> set[str]:
    """Return the keys of already-seen vacancies, for dedup before tokens are spent."""
    try:
        items = await store.asearch(jobs_ns(user_id), limit=1000)
    except Exception as exc:
        logger.warning("Could not read known vacancies (%s); dedup skipped", exc)
        return set()
    return {item.key for item in items}


async def load_profile(store: BaseStore, user_id: str) -> dict | None:
    """Load the stored Candidate Profile, if one exists."""
    item = await store.aget(profile_ns(user_id), "current")
    return dict(item.value) if item else None


async def save_profile(store: BaseStore, user_id: str, profile: Any) -> None:
    """Persist the Candidate Profile."""
    await store.aput(profile_ns(user_id), "current", profile.model_dump(mode="json"))


async def load_taxonomy(store: BaseStore) -> dict | None:
    """Load the track taxonomy, if it has been built."""
    item = await store.aget(taxonomy_ns(), "current")
    return dict(item.value) if item else None


async def save_taxonomy(store: BaseStore, taxonomy: Any) -> None:
    """Persist the track taxonomy."""
    await store.aput(taxonomy_ns(), "current", taxonomy.model_dump(mode="json"))


async def load_feedback(store: BaseStore, user_id: str) -> dict[str, Any]:
    """Load stop-lists and preferences accumulated from the user's replies."""
    item = await store.aget(feedback_ns(user_id), "current")
    return dict(item.value) if item else {"company_deny": [], "notes": []}


async def save_feedback(store: BaseStore, user_id: str, data: dict[str, Any]) -> None:
    """Persist accumulated user preferences."""
    await store.aput(feedback_ns(user_id), "current", data)
