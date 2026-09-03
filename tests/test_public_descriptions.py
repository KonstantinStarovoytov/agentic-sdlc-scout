"""Requirements without an account: descriptions from public job pages.

A container runs without LinkedIn MCP by design. Until the public page was read,
that meant every posting was saved with an empty description, the extractor had
nothing but a title to work from, and the rubric scored 124 postings at ten
points each with `requirements: 0` on every line. The scoring was not wrong; it
had nothing to score.

The second half covers search wording. LinkedIn's guest search ranks rather than
filters: the query "Agentic SDLC Engineer" returned none of the five Warsaw
postings titled "Agentic SDLC Senior Engineer", while the exact title returned
all five. The tracked roles are therefore phrased as postings phrase them and
are always searched, whatever else the model asks for.
"""

from __future__ import annotations

from datetime import date

import pytest

from scout.graphs.research import _merge_roles
from scout.schemas import JobPosting, Seniority
from scout.tools.guest_jobs import parse_job_description


def make_posting(job_id: str) -> JobPosting:
    return JobPosting(
        canonical_id=f"li:{job_id}",
        title="Agentic SDLC Senior Engineer",
        company="Acme",
        location="Warsaw",
        seniority=Seniority.SENIOR,
        posted_at=date.today(),
    )

PUBLIC_PAGE = """
<html><body>
<section class="description">
  <div class="show-more-less-html__markup">
    <p>We are looking for a Senior AI/ML Engineer for Agentic SDLC solutions.</p>
    <ul><li>5+ years in a technical role</li><li>GitHub Copilot, MCP</li></ul>
  </div>
</section>
</body></html>
"""

AUTH_WALL = "<html><body><div class='authwall'>Sign in to continue</div></body></html>"


class TestPublicPageParsing:
    def test_description_is_extracted_as_text(self):
        text = parse_job_description(PUBLIC_PAGE)

        assert text is not None
        assert "Agentic SDLC solutions" in text
        assert "5+ years in a technical role" in text
        assert "<li>" not in text

    def test_page_without_a_description_yields_nothing(self):
        assert parse_job_description(AUTH_WALL) is None
        assert parse_job_description("") is None

    def test_older_markup_is_still_read(self):
        legacy = '<div class="description__text">Legacy description body</div>'

        assert parse_job_description(legacy) == "Legacy description body"


class TestTrackedRolesAreAFloor:
    def test_config_roles_come_first_and_survive_a_model_list(self):
        tracked = ["Agentic SDLC Engineer", "Agentic SDLC Senior Engineer"]

        merged = _merge_roles(tracked, ["AI Engineer", "LLM Engineer"])

        assert merged[:2] == tracked
        assert "AI Engineer" in merged and "LLM Engineer" in merged

    def test_duplicates_are_folded_case_insensitively(self):
        merged = _merge_roles(["AI Engineer"], ["ai engineer", " AI Engineer "])

        assert merged == ["AI Engineer"]

    def test_no_extra_roles_is_just_the_config(self):
        assert _merge_roles(["A", "B"], None) == ["A", "B"]


class TestFullReadsAreNotCapped:
    """A read of "everything" must return everything, past any single page."""

    @pytest.mark.asyncio
    async def test_search_all_pages_past_one_page(self):
        from langgraph.store.memory import InMemoryStore

        from scout.memory import _PAGE, search_all

        store = InMemoryStore()
        ns = ("t", "jobs")
        total = _PAGE * 2 + 45
        for i in range(total):
            await store.aput(ns, f"li:{i}", {"i": i})

        items = await search_all(store, ns)

        assert len(items) == total
        assert len({item.key for item in items}) == total

    @pytest.mark.asyncio
    async def test_list_known_jobs_sees_the_whole_corpus(self, monkeypatch):
        from langgraph.store.memory import InMemoryStore

        from scout.memory import _PAGE, jobs_ns
        from scout.tools import analysis

        store = InMemoryStore()
        ns = jobs_ns("owner")
        for i in range(_PAGE + 20):
            await store.aput(ns, f"li:{i}", make_posting(str(i)).model_dump(mode="json"))
        target = make_posting("target").model_copy(update={"title": "Agentic SDLC Engineer"})
        await store.aput(ns, target.canonical_id, target.model_dump(mode="json"))

        monkeypatch.setattr(analysis, "_store", lambda: store)
        monkeypatch.setattr(analysis, "current_user_id", lambda: "owner")

        out = await analysis.list_known_jobs.ainvoke({"title_contains": "SDLC Engineer"})

        assert "li:target" in out
        assert f"of {_PAGE + 21} stored" in out


class TestEnrichFallsBackToPublicPages:
    """Without an account the node reads public pages; it does not give up."""

    @pytest.mark.asyncio
    async def test_public_page_fills_the_description(self, monkeypatch):
        from scout.graphs import research
        from scout.tools import guest_jobs


        fetched: list[str] = []

        async def no_tools() -> list:
            return []

        async def fake_fetch(self, job_id: str) -> str | None:
            fetched.append(job_id)
            return f"Full description for {job_id}"

        async def no_sleep(_: float) -> None:
            return None

        monkeypatch.setattr("scout.tools.linkedin_mcp.build_linkedin_tools", no_tools)
        monkeypatch.setattr(guest_jobs.GuestJobsClient, "fetch_description", fake_fetch)
        monkeypatch.setattr(research.asyncio, "sleep", no_sleep)

        fresh = [make_posting("111"), make_posting("222")]
        result = await research.enrich_node({"fresh": fresh}, runtime=None)  # type: ignore[arg-type]

        assert fetched == ["111", "222"]
        assert [j.description for j in result["enriched"]] == [
            "Full description for 111",
            "Full description for 222",
        ]
        assert not any("no full description" in n for n in result["notes"])

    @pytest.mark.asyncio
    async def test_public_budget_is_respected_and_reported(self, monkeypatch):
        from scout.graphs import research
        from scout.tools import guest_jobs


        async def no_tools() -> list:
            return []

        async def fake_fetch(self, job_id: str) -> str | None:
            return "text"

        async def no_sleep(_: float) -> None:
            return None

        monkeypatch.setattr("scout.tools.linkedin_mcp.build_linkedin_tools", no_tools)
        monkeypatch.setattr(guest_jobs.GuestJobsClient, "fetch_description", fake_fetch)
        monkeypatch.setattr(research.asyncio, "sleep", no_sleep)
        monkeypatch.setattr(
            research.get_config().budgets, "public_page_fetches_per_run", 1, raising=False
        )

        fresh = [make_posting("1"), make_posting("2"), make_posting("3")]
        result = await research.enrich_node({"fresh": fresh}, runtime=None)  # type: ignore[arg-type]

        described = [j for j in result["enriched"] if j.description]
        assert len(described) == 1
        assert any("2 of 3 vacancies have no full description" in n for n in result["notes"])
