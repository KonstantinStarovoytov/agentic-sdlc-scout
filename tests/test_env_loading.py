"""`.env` has to reach the process environment, not just our own settings.

Four separate features were configured correctly in `.env` and silently did
nothing, because each was consumed by a library that reads `os.environ` and
never sees a pydantic model. LangSmith tracing was the clearest: the key and the
flag were both set and no trace was ever recorded.
"""

from __future__ import annotations

import os

from scout.config import Settings, load_env_file

ENV_BODY = """\
# a comment
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_from_the_file
LANGSMITH_PROJECT=agentic-sdlc-scout
EMPTY_VALUE=
"""


def _write_env(tmp_path):
    path = tmp_path / ".env"
    path.write_text(ENV_BODY, encoding="utf-8")
    return path


class TestLoadEnvFile:
    def test_values_reach_the_environment(self, tmp_path, monkeypatch):
        for key in ("LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT"):
            monkeypatch.delenv(key, raising=False)

        load_env_file(_write_env(tmp_path))

        assert os.environ["LANGSMITH_TRACING"] == "true"
        assert os.environ["LANGSMITH_API_KEY"] == "lsv2_from_the_file"
        assert os.environ["LANGSMITH_PROJECT"] == "agentic-sdlc-scout"

    def test_a_real_environment_variable_wins(self, tmp_path, monkeypatch):
        """Same precedence Settings uses, so the two cannot disagree."""
        monkeypatch.setenv("LANGSMITH_PROJECT", "set-by-the-shell")

        load_env_file(_write_env(tmp_path))

        assert os.environ["LANGSMITH_PROJECT"] == "set-by-the-shell"

    def test_a_missing_file_is_not_an_error(self, tmp_path):
        load_env_file(tmp_path / "absent")


class TestTracingIsVisible:
    def test_tracing_needs_both_the_flag_and_the_key(self):
        assert Settings(langsmith_tracing=True, langsmith_api_key="k", _env_file=None).has_langsmith
        assert not Settings(
            langsmith_tracing=False, langsmith_api_key="k", _env_file=None
        ).has_langsmith
        assert not Settings(
            langsmith_tracing=True, langsmith_api_key=None, _env_file=None
        ).has_langsmith

    def test_the_settings_know_about_langsmith_at_all(self):
        """`extra="ignore"` used to drop these three without a word."""
        fields = Settings.model_fields
        assert {"langsmith_tracing", "langsmith_api_key", "langsmith_project"} <= set(fields)
