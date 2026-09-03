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


def _pool_config() -> dict[str, Any]:
    """Pool settings that survive Neon's free tier.

    Neon suspends the compute after about five minutes without traffic and drops
    every open connection with it. A pool that then hands out the connection it
    has been holding produces "SSL connection has been closed unexpectedly" on
    the first query of the day — which is how one Candidate Profile was built,
    paid for and lost in the same run.

    Three settings address it. `check` pings a connection before it is handed
    out and discards it if dead, at the cost of one round trip per checkout.
    `max_idle` retires connections that have sat unused for longer than Neon
    tolerates, so the pool rarely holds one that has been closed under it.
    `max_lifetime` recycles everything periodically regardless. The timeout is
    generous because a suspended compute takes seconds to wake.
    """
    from psycopg_pool import AsyncConnectionPool

    return {
        "min_size": 1,
        "max_size": 5,
        "timeout": 30.0,
        "check": AsyncConnectionPool.check_connection,
        "max_idle": 180.0,
        "max_lifetime": 1800.0,
    }


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
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    url = cfg.scout_database_url or ""
    pool_config = _pool_config()

    # The checkpointer gets its own pool rather than `from_conn_string`, which
    # opens a single connection and holds it for the life of the process.
    # Everything said about Neon in `_pool_config` applies to it too, and it is
    # the first thing touched on every turn.
    async with contextlib.AsyncExitStack() as stack:
        try:
            store = await stack.enter_async_context(
                AsyncPostgresStore.from_conn_string(
                    url, index=_index_config(cfg), pool_config=pool_config
                )
            )
            saver_pool = await stack.enter_async_context(
                AsyncConnectionPool(
                    url,
                    kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                    **pool_config,
                )
            )
            saver = AsyncPostgresSaver(conn=saver_pool)
            await store.setup()
            await saver.setup()
        except Exception as exc:
            # Only connecting is allowed to fall back. The `yield` used to sit
            # inside this `try`, so an error raised by the caller's own work —
            # a bad API key during an embedding, say — was caught here, logged
            # as "Postgres is unavailable", and answered with a second yield,
            # which a context manager may not do. The real error was buried
            # under "generator didn't stop after athrow()".
            logger.warning("Postgres is unavailable (%s): falling back to in-memory", exc)
            async with _open_in_memory() as pair:
                yield pair
            return

        yield store, saver


@contextlib.asynccontextmanager
async def _open_in_memory() -> AsyncIterator[tuple[BaseStore, BaseCheckpointSaver]]:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    yield InMemoryStore(), InMemorySaver()


async def put_job(store: BaseStore, user_id: str, job: Any) -> None:
    """Store a full dossier. Only the card ever reaches the agent's context."""
    await store.aput(jobs_ns(user_id), job.canonical_id, job.model_dump(mode="json"))


_PAGE = 200


async def search_all(store: BaseStore, namespace: tuple[str, ...]) -> list[Any]:
    """Every item in a namespace, paged, because `asearch` caps at its `limit`.

    Two callers used a single call with a round number — 200 for listing, 1000
    for dedup — and both numbers were fine until the corpus outgrew them. Past
    the cap, listing silently reported "none match" for postings that were
    there, and dedup would have started paying to extract postings it already
    held. A cap on a full read is not a bound; it is a bug waiting for growth.
    """
    items: list[Any] = []
    offset = 0
    while True:
        page = await store.asearch(namespace, limit=_PAGE, offset=offset)
        items.extend(page)
        if len(page) < _PAGE:
            return items
        offset += _PAGE


async def get_known_job_ids(store: BaseStore, user_id: str) -> set[str]:
    """Return the keys of already-seen vacancies, for dedup before tokens are spent."""
    try:
        items = await search_all(store, jobs_ns(user_id))
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
