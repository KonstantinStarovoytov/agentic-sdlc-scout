"""Finding a vacancy again after it stops being new.

`research_jobs` reports only first sightings, which is right for the context
budget and wrong for the user: the best match disappears from every subsequent
answer. It happened on a real run — an "Agentic SDLC Engineer" posting sat in
memory while the agent reported eighteen unrelated new vacancies and never
mentioned it, because nothing in the toolset could look at what was already
stored.
"""

from __future__ import annotations

import pytest
from langgraph.store.memory import InMemoryStore

from scout.memory import jobs_ns
from scout.schemas import JobPosting, Seniority, WorkMode
from scout.tools.analysis import list_known_jobs
from scout.tools.profile_ingest import extract_text_from_file


def posting(job_id: str, title: str, company: str, mode: WorkMode, posted: str) -> JobPosting:
    return JobPosting(
        canonical_id=f"li:{job_id}",
        source="linkedin_guest",
        external_id=job_id,
        title=title,
        company=company,
        location="Warsaw, Mazowieckie, Poland",
        work_mode=mode,
        seniority=Seniority.SENIOR,
        posted_at=posted,
    )


STORED = [
    posting("1", "Agentic SDLC Engineer (f/m/x)", "Sii Poland", WorkMode.ONSITE, "2026-08-30"),
    posting("2", "Senior Automation Engineer", "Nomagic", WorkMode.ONSITE, "2026-09-01"),
    posting("3", "AI Platform Engineer", "Lenovo", WorkMode.REMOTE, "2026-08-20"),
]


@pytest.fixture
def store(monkeypatch):
    memory = InMemoryStore()
    for job in STORED:
        memory.put(jobs_ns("owner"), job.canonical_id, job.model_dump(mode="json"))
    monkeypatch.setattr("scout.tools.analysis._store", lambda: memory)
    return memory


class TestListKnownJobs:
    async def test_a_vacancy_that_is_no_longer_new_is_still_findable(self, store):
        """The defect that prompted this tool, stated as a test."""
        result = await list_known_jobs.ainvoke({"title_contains": "agentic"})
        assert "Agentic SDLC Engineer" in result
        assert "Sii Poland" in result

    async def test_the_filter_excludes_what_does_not_match(self, store):
        result = await list_known_jobs.ainvoke({"title_contains": "agentic"})
        assert "Nomagic" not in result

    async def test_matching_is_case_insensitive(self, store):
        assert "Sii Poland" in await list_known_jobs.ainvoke({"title_contains": "AGENTIC SDLC"})

    async def test_everything_comes_back_without_a_filter(self, store):
        result = await list_known_jobs.ainvoke({})
        assert all(job.company in result for job in STORED)

    async def test_work_mode_filters(self, store):
        result = await list_known_jobs.ainvoke({"work_mode": "onsite"})
        assert "Sii Poland" in result and "Lenovo" not in result

    async def test_newest_first(self, store):
        result = await list_known_jobs.ainvoke({})
        assert result.index("Nomagic") < result.index("Sii Poland") < result.index("Lenovo")

    async def test_an_empty_match_says_how_many_were_searched(self, store):
        """"Nothing found" and "nothing stored" call for different next steps."""
        result = await list_known_jobs.ainvoke({"title_contains": "quantum"})
        assert "3 vacancies in memory" in result

    async def test_empty_memory_points_at_research(self, monkeypatch):
        monkeypatch.setattr("scout.tools.analysis._store", lambda: InMemoryStore())
        assert "research_jobs" in await list_known_jobs.ainvoke({})

    async def test_no_store_is_reported_rather_than_raised(self, monkeypatch):
        monkeypatch.setattr("scout.tools.analysis._store", lambda: None)
        assert "unavailable" in (await list_known_jobs.ainvoke({})).lower()

    async def test_the_ids_come_back_so_the_agent_can_score_them(self, store):
        """Without the id the listing is a dead end: score_jobs takes ids."""
        assert "[li:1]" in await list_known_jobs.ainvoke({"title_contains": "agentic"})


class TestCvPathErrors:
    def test_a_directory_says_so_instead_of_blaming_the_format(self, tmp_path):
        """A folder used to surface as "Unsupported format: .", which misleads."""
        with pytest.raises(ValueError, match="is a directory"):
            extract_text_from_file(tmp_path)

    def test_a_missing_file_is_still_a_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            extract_text_from_file(tmp_path / "absent.pdf")
