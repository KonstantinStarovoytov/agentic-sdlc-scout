"""The guest source parser, tested against recorded HTML.

LinkedIn changes its markup without warning, which makes this the most fragile
part of the system. The fixture was captured from the live endpoint on
2026-09-03; if these tests turn red without the code being touched, refresh the
fixture first and look at what changed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scout.schemas import Seniority, WorkMode
from scout.tools.guest_jobs import guess_seniority, parse_job_cards

FIXTURE = Path(__file__).parent / "fixtures" / "guest_jobs_sample.html"


@pytest.fixture
def sample_html() -> str:
    if not FIXTURE.exists():
        pytest.skip("guest_jobs_sample.html fixture is missing")
    return FIXTURE.read_text(encoding="utf-8")


class TestParser:
    def test_extracts_jobs(self, sample_html):
        jobs = parse_job_cards(sample_html)
        assert jobs, "the fixture must contain vacancies"

    def test_every_job_has_required_fields(self, sample_html):
        for job in parse_job_cards(sample_html):
            assert job.title and job.company
            assert job.canonical_id

    def test_linkedin_ids_are_recognised(self, sample_html):
        jobs = parse_job_cards(sample_html)
        assert any(job.canonical_id.startswith("li:") for job in jobs)

    def test_ids_are_unique(self, sample_html):
        jobs = parse_job_cards(sample_html)
        assert len({j.canonical_id for j in jobs}) == len(jobs)

    def test_work_mode_is_propagated(self, sample_html):
        jobs = parse_job_cards(sample_html, work_mode=WorkMode.REMOTE)
        assert all(job.work_mode is WorkMode.REMOTE for job in jobs)

    def test_empty_html_returns_nothing(self):
        assert parse_job_cards("") == []

    def test_garbage_html_does_not_crash(self):
        assert parse_job_cards("<li><div>no title here</div></li>") == []


class TestSeniorityGuess:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Senior AI Engineer", Seniority.SENIOR),
            ("Sr. Backend Developer", Seniority.SENIOR),
            ("Junior Python Developer", Seniority.JUNIOR),
            ("Staff Software Engineer", Seniority.STAFF),
            ("Engineering Intern", Seniority.INTERN),
            ("Principal Architect", Seniority.PRINCIPAL),
            ("Head of Engineering", Seniority.VP),
            ("AI Engineer", Seniority.UNKNOWN),
        ],
    )
    def test_levels(self, title, expected):
        assert guess_seniority(title) is expected

    def test_stronger_level_wins_over_senior(self):
        """A "Senior Staff Engineer" is staff, not senior."""
        assert guess_seniority("Senior Staff Engineer") is Seniority.STAFF
