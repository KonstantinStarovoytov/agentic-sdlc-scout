"""Tests for the prefilter and the assembly of the subgraph.

The prefilter is where LinkedIn requests are saved, and with them the risk to the
account. A mistake here either lets junk through or silently discards suitable
vacancies.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from scout.config import ScoutConfig
from scout.graphs.research import build_research_graph, format_cards, passes_prefilter
from scout.schemas import JobPosting, Seniority


@pytest.fixture
def config() -> ScoutConfig:
    cfg = ScoutConfig()
    cfg.search.freshness_days = 30
    cfg.filters.seniority_allow = ["mid", "senior", "staff", "lead"]
    cfg.filters.seniority_deny = ["intern", "junior", "principal", "director", "vp"]
    cfg.filters.title_deny_keywords = ["sales", "recruiter"]
    cfg.filters.company_deny = ["BadCorp"]
    return cfg


def _job(**kwargs) -> JobPosting:
    defaults: dict = {
        "canonical_id": "li:1",
        "title": "Senior AI Engineer",
        "company": "Acme",
        "location": "Warsaw",
        "seniority": Seniority.SENIOR,
        "posted_at": date.today() - timedelta(days=3),
    }
    defaults.update(kwargs)
    return JobPosting(**defaults)


class TestPrefilter:
    def test_good_job_passes(self, config):
        ok, reason = passes_prefilter(_job(), config)
        assert ok and reason is None

    def test_denied_title_keyword(self, config):
        ok, reason = passes_prefilter(_job(title="Sales Engineer"), config)
        assert not ok and "stop word" in reason

    def test_denied_company(self, config):
        ok, reason = passes_prefilter(_job(company="BadCorp"), config)
        assert not ok and "stop-list" in reason

    def test_company_denylist_is_case_insensitive(self, config):
        ok, _ = passes_prefilter(_job(company="badcorp"), config)
        assert not ok

    def test_feedback_extends_denylist(self, config):
        """The user's reaction must influence later runs."""
        ok, reason = passes_prefilter(_job(company="Meh Inc"), config, denied_companies={"meh inc"})
        assert not ok and "stop-list" in reason

    def test_seniority_out_of_range(self, config):
        ok, reason = passes_prefilter(_job(seniority=Seniority.JUNIOR), config)
        assert not ok and "seniority" in reason

    def test_unknown_seniority_passes(self, config):
        """An unknown level is not a reason to discard a vacancy."""
        ok, _ = passes_prefilter(_job(seniority=Seniority.UNKNOWN), config)
        assert ok

    def test_stale_job_is_dropped(self, config):
        ok, reason = passes_prefilter(_job(posted_at=date.today() - timedelta(days=90)), config)
        assert not ok and "freshness" in reason

    def test_missing_date_passes(self, config):
        ok, _ = passes_prefilter(_job(posted_at=None), config)
        assert ok


class TestCardFormatting:
    def test_empty_result_is_explicit(self):
        text = format_cards([], {"scanned": 0}, [])
        assert "No new vacancies found" in text

    def test_notes_are_surfaced(self):
        text = format_cards([], {}, ["LinkedIn MCP is not connected"])
        assert "Limitations of this run" in text
        assert "LinkedIn MCP is not connected" in text

    def test_cards_stay_compact(self):
        """A card is one line: it is the only thing that travels into the context."""
        jobs = [_job(canonical_id=f"li:{i}", title=f"Engineer {i}").card() for i in range(30)]
        text = format_cards(jobs, {}, [])
        body = text.split("Stats")[0]
        assert len(body.splitlines()) <= 33

    def test_reminds_agent_not_to_pull_full_descriptions(self):
        text = format_cards([_job().card()], {}, [])
        assert "job-analyst" in text


class TestGraphAssembly:
    def test_graph_compiles_with_expected_nodes(self):
        graph = build_research_graph()
        nodes = set(graph.get_graph().nodes)
        assert {"scan", "dedupe", "enrich", "extract", "persist"} <= nodes

    def test_extract_runs_after_enrich(self):
        """Order matters: there is nothing to extract until the description arrives."""
        graph = build_research_graph()
        edges = {(e.source, e.target) for e in graph.get_graph().edges}
        assert ("enrich", "extract") in edges
        assert ("extract", "persist") in edges
