"""Where the Candidate Profile takes its facts from.

Two failures motivated these tests, and both were silent — the profile was
assembled, the run reported success, and the content was simply wrong.

The first: `get_person_profile` was called with the wrong argument name. The
server answers a bad call by returning the validation error as ordinary content
rather than by raising, so the caller stringified a pydantic traceback and
offered it to the model as the user's career.

The second: an attached CV never reached the tool. The profile was rebuilt from
whatever file happened to sit in `data/private`, which is a confident answer
about a possibly year-old document.
"""

from __future__ import annotations

import json

import pytest

from scout.tools.linkedin_mcp import profile_text_from
from scout.tools.profile_ingest import bootstrap_profile


class TestProfileResultParsing:
    def test_a_validation_error_is_not_a_profile(self):
        raw = [
            {
                "type": "text",
                "text": (
                    "2 validation errors for call[get_person_profile]\n"
                    "linkedin_username\n  Missing required argument "
                    "[type=missing_argument, input_value={'linkedin_url': '...'}]"
                ),
            }
        ]

        assert profile_text_from(raw) == ""

    def test_an_error_document_is_not_a_profile(self):
        raw = [{"type": "text", "text": json.dumps({"error": "session expired"})}]

        assert profile_text_from(raw) == ""

    def test_sections_are_joined_under_their_names(self):
        raw = [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "sections": {
                            "main_profile": "Konstantin Starovoytov\nLead Automation Engineer",
                            "experience": "Senior software developer in test\nPlaytika",
                            "empty": "   ",
                        }
                    }
                ),
            }
        ]

        text = profile_text_from(raw)

        assert "## main_profile" in text
        assert "## experience" in text
        assert "Playtika" in text
        assert "## empty" not in text

    def test_plain_text_survives_unparsed(self):
        raw = [{"type": "text", "text": "Konstantin Starovoytov — Playtika"}]

        assert profile_text_from(raw) == "Konstantin Starovoytov — Playtika"


class TestAttachedCVWins:
    """An attachment states which document the user means; disk does not."""

    @pytest.mark.asyncio
    async def test_supplied_text_beats_the_stored_file(self, capture_sources, tmp_path):
        stale = tmp_path / "cv.md"
        stale.write_text("Stale CV from a year ago", encoding="utf-8")

        await bootstrap_profile.ainvoke(
            {"cv_path": str(stale), "cv_text": "Fresh CV pasted into the chat"}
        )

        assert "Fresh CV pasted into the chat" in capture_sources["cv"]
        assert "Stale" not in capture_sources["cv"]

    @pytest.mark.asyncio
    async def test_blank_text_falls_back_to_the_file(self, capture_sources, tmp_path):
        stored = tmp_path / "cv.md"
        stored.write_text("The CV that lives on disk", encoding="utf-8")

        await bootstrap_profile.ainvoke({"cv_path": str(stored), "cv_text": "   "})

        assert "The CV that lives on disk" in capture_sources["cv"]

    @pytest.mark.asyncio
    async def test_the_file_is_still_the_default(self, capture_sources, tmp_path):
        stored = tmp_path / "cv.md"
        stored.write_text("The CV that lives on disk", encoding="utf-8")

        await bootstrap_profile.ainvoke({"cv_path": str(stored)})

        assert "The CV that lives on disk" in capture_sources["cv"]


class TestContactsAreASideEffect:
    """A contacts file that cannot be written must not take the run down with it.

    In the container `data/private` was mounted read-only, and the write raised
    an OSError after every source had been read and the model call paid for.
    """

    def test_unwritable_location_is_reported_not_raised(self, monkeypatch, tmp_path):
        from scout.tools import profile_ingest, render_pdf

        blocked = tmp_path / "private"
        blocked.mkdir()
        blocked.chmod(0o500)
        monkeypatch.setattr(render_pdf, "CONTACTS_PATH", blocked / "contacts.json")

        try:
            note = profile_ingest._store_contacts({"email": "a@b.c"})
        finally:
            blocked.chmod(0o700)

        assert note is not None
        assert "could not be saved" in note

    def test_writable_location_returns_nothing(self, monkeypatch, tmp_path):
        from scout.tools import profile_ingest, render_pdf

        path = tmp_path / "private" / "contacts.json"
        monkeypatch.setattr(render_pdf, "CONTACTS_PATH", path)

        assert profile_ingest._store_contacts({"email": "a@b.c"}) is None
        assert json.loads(path.read_text())["email"] == "a@b.c"


@pytest.fixture
def capture_sources(monkeypatch):
    """Run `bootstrap_profile` for real, but stop at the model call.

    The decision under test is which text ends up in the `cv` source; the merge
    that follows is a paid call to a provider and proves nothing about it.
    """
    from scout.tools import profile_ingest

    captured: dict[str, str] = {}

    async def no_linkedin(*args, **kwargs) -> str:
        return ""

    async def no_site(*args, **kwargs) -> str:
        return ""

    class StopAtMerge:
        def with_structured_output(self, *args, **kwargs):
            return self

        async def ainvoke(self, messages, *args, **kwargs):
            for message in messages:
                if message["role"] == "user":
                    captured["cv"] = message["content"]
            raise _Stop

    monkeypatch.setattr(profile_ingest, "_fetch_linkedin", no_linkedin)
    monkeypatch.setattr(profile_ingest, "_fetch_site", no_site)
    monkeypatch.setattr(profile_ingest, "_store_contacts", lambda contacts: None)
    monkeypatch.setattr(profile_ingest, "chat_model", lambda *a, **k: StopAtMerge())

    settings = profile_ingest.get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "test-key", raising=False)

    original = profile_ingest.bootstrap_profile.coroutine

    async def swallow_stop(*args, **kwargs):
        try:
            return await original(*args, **kwargs)
        except _Stop:
            return "stopped at the merge"

    monkeypatch.setattr(profile_ingest.bootstrap_profile, "coroutine", swallow_stop)
    return captured


class _Stop(Exception):
    """Ends the run once the sources have been assembled."""
