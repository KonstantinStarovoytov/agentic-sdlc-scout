"""Credentials have to travel from settings into the provider client.

The bug these guard against was invisible for as long as a stale `OPENAI_API_KEY`
was exported from a shell profile: `init_chat_model` reads the environment, so
the key in `.env` was loaded, checked and never used. Removing the export turned
a working-looking agent into one with no credentials at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scout import models
from scout.config import Settings
from scout.memory import _index_config
from scout.models import MissingCredentialsError, chat_model, embeddings_model

SETTINGS_KEY = "sk-test-from-settings"


def _settings(key: str | None) -> Settings:
    return Settings(openai_api_key=key, _env_file=None)


def _configured_key(model) -> str:
    """The key the provider client actually ended up holding."""
    return model.openai_api_key.get_secret_value()


class TestCredentialsReachTheClient:
    def test_the_key_comes_from_settings_not_the_environment(self, monkeypatch):
        """The regression: with nothing exported, the .env key must still be used."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(models, "get_settings", lambda: _settings(SETTINGS_KEY))

        assert _configured_key(chat_model("openai:gpt-4.1-mini")) == SETTINGS_KEY

    def test_settings_win_over_a_different_ambient_key(self, monkeypatch):
        """Settings have already resolved precedence; their answer is the final one.

        A stale export must not be able to quietly replace the configured key,
        which is exactly how the original failure hid for so long.
        """
        monkeypatch.setenv("OPENAI_API_KEY", "sk-stale-from-the-shell")
        monkeypatch.setattr(models, "get_settings", lambda: _settings(SETTINGS_KEY))

        assert _configured_key(chat_model("openai:gpt-4.1-mini")) == SETTINGS_KEY

    def test_no_key_fails_at_assembly_rather_than_mid_run(self, monkeypatch):
        """Better a refusal to build than a run that dies on its first model call."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(models, "get_settings", lambda: _settings(None))

        with pytest.raises(MissingCredentialsError, match="OPENAI_API_KEY"):
            chat_model("openai:gpt-4.1-mini")

    def test_extra_arguments_still_reach_the_model(self, monkeypatch):
        monkeypatch.setattr(models, "get_settings", lambda: _settings(SETTINGS_KEY))
        assert chat_model("openai:gpt-4.1-mini", temperature=0).temperature == 0


class TestEmbeddings:
    def test_the_key_comes_from_settings_not_the_environment(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(models, "get_settings", lambda: _settings(SETTINGS_KEY))

        model = embeddings_model("openai:text-embedding-3-small")
        assert model.openai_api_key.get_secret_value() == SETTINGS_KEY

    def test_no_key_is_refused(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(models, "get_settings", lambda: _settings(None))

        with pytest.raises(MissingCredentialsError):
            embeddings_model("openai:text-embedding-3-small")

    def test_the_store_index_carries_a_built_model_not_a_name(self, monkeypatch):
        """A name would be resolved inside the store, against the environment.

        When that failed the store fell back to in-memory and the run continued
        without persisting anything — a quiet way to lose every job dossier.
        """
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(models, "get_settings", lambda: _settings(SETTINGS_KEY))

        index = _index_config(_settings(SETTINGS_KEY))
        assert index is not None
        assert not isinstance(index["embed"], str)
        assert index["embed"].openai_api_key.get_secret_value() == SETTINGS_KEY

    def test_the_index_is_dropped_when_there_is_no_key(self):
        """Semantic search is optional; persistence is not. Degrade, do not raise."""
        assert _index_config(_settings(None)) is None


class TestNoDirectModelConstruction:
    @pytest.mark.parametrize("entry_point", ["init_chat_model", "init_embeddings"])
    def test_only_the_models_module_builds_models(self, entry_point):
        """One place builds models, so one place can be sure about credentials.

        A new call anywhere else would reintroduce the bug in a form no unit test
        on the existing call sites would notice.
        """
        source_root = Path(__file__).resolve().parents[1] / "src" / "scout"
        offenders = [
            path.relative_to(source_root).as_posix()
            for path in source_root.rglob("*.py")
            if path.name != "models.py" and entry_point in path.read_text(encoding="utf-8")
        ]
        assert offenders == [], (
            f"These modules call {entry_point} directly and would bypass the key "
            f"from settings: {offenders}. Use scout.models instead."
        )
