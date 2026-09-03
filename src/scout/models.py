"""Chat models built from the project's own settings.

`init_chat_model` resolves credentials the way the provider SDK does: out of the
process environment. A key that lives only in `.env` therefore never reaches the
client, and the failure is confusing rather than loud — the agent starts, the
run proceeds, and only the first model call reports missing credentials.

That is not hypothetical. It stayed hidden here for as long as a stale
`OPENAI_API_KEY` happened to be exported from a shell profile: the value in
`.env` was read, validated and never used, while every model quietly ran on the
environment's key instead.

So every model in the project is built through this module, with the key passed
explicitly. `Settings` has already resolved precedence between the environment
and `.env`, and its answer is the one that should reach the provider.
"""

from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from .config import get_settings


class MissingCredentialsError(RuntimeError):
    """No API key is configured, so no model can be built."""


def chat_model(name: str, **kwargs: Any) -> BaseChatModel:
    """Build a chat model with credentials taken from settings.

    Args:
        name: model identifier in `provider:model` form, as in `search.yaml`.
        **kwargs: passed through to `init_chat_model`.

    Returns:
        The configured model.

    Raises:
        MissingCredentialsError: when no API key is configured. Raised here, at
            assembly time, rather than leaving the provider to fail on the first
            call somewhere deep inside a run.
    """
    return init_chat_model(name, api_key=_require_key(), **kwargs)


def embeddings_model(name: str, **kwargs: Any) -> Embeddings:
    """Build an embeddings model with credentials taken from settings.

    Separate from `chat_model` only because the provider entry point differs;
    the reason both exist is the same. The store's semantic index used to be
    configured with the model *name*, leaving the resolution — and therefore the
    credential lookup — to happen inside the store against the environment. When
    that failed the store fell back to in-memory and the run carried on without
    persistence, which is a quiet way to lose every job dossier.

    Args:
        name: model identifier in `provider:model` form.
        **kwargs: passed through to `init_embeddings`.

    Returns:
        The configured embeddings model.

    Raises:
        MissingCredentialsError: when no API key is configured.
    """
    return init_embeddings(name, api_key=_require_key(), **kwargs)


def _require_key() -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        raise MissingCredentialsError(
            "OPENAI_API_KEY is not set. Put it in .env at the repository root "
            "(copy .env.example if there is no .env yet). Note that a key exported "
            "in the shell environment takes precedence over the file."
        )
    return settings.openai_api_key
