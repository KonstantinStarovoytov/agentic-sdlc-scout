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
    settings = get_settings()
    if not settings.openai_api_key:
        raise MissingCredentialsError(
            "OPENAI_API_KEY is not set. Put it in .env at the repository root "
            "(copy .env.example if there is no .env yet). Note that a key exported "
            "in the shell environment takes precedence over the file."
        )
    return init_chat_model(name, api_key=settings.openai_api_key, **kwargs)
