"""Unit tests for the rubric and normalisation. No LLM: this is where the nasty bugs live."""

from __future__ import annotations

import pytest

from scout.config import ScoutConfig
from scout.schemas import (
    CandidateProfile,
    FitVerdict,
    JobPosting,
    ProfileClaim,
    Requirement,
    RequirementKind,
    Seniority,
    WorkMode,
    canonical_job_id,
    normalize_skill,
)
from scout.scoring import aggregate_gaps, check_hard_gate, score_job, seniority_fit


@pytest.fixture
def config() -> ScoutConfig:
    cfg = ScoutConfig()
    cfg.search.locations = ["Warsaw, Mazowieckie, Poland", "Poland"]
    return cfg


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(
        user_id="test",
        years_experience=8,
        work_authorization="EU citizen",
        languages=["en", "pl"],
        claims=[
            ProfileClaim(skill="Python", evidence="8 years building backend services in Python"),
            ProfileClaim(skill="Kubernetes", evidence="Ran production workloads on Kubernetes"),
            ProfileClaim(skill="LangChain", evidence="Built an internal agent on LangChain"),
        ],
    )


def _job(**kwargs) -> JobPosting:
    defaults: dict = {
        "canonical_id": "li:1",
        "title": "AI Engineer",
        "company": "Acme",
        "location": "Warsaw, Mazowieckie, Poland",
        "work_mode": WorkMode.HYBRID,
        "seniority": Seniority.SENIOR,
    }
    defaults.update(kwargs)
    return JobPosting(**defaults)


class TestNormalization:
    def test_aliases_collapse(self):
        assert normalize_skill("K8s") == "kubernetes"
        assert normalize_skill("  LLMs ") == "large language models"
        assert normalize_skill("CI/CD") == "ci/cd"

    def test_punctuation_stripped_but_plus_kept(self):
        assert normalize_skill("C++") == "c++"
        assert normalize_skill("Node.js") == "node.js"

    def test_case_and_space_insensitive(self):
        assert normalize_skill("Machine  Learning") == normalize_skill("machine learning")


class TestCanonicalId:
    def test_linkedin_id_wins(self):
        got = canonical_job_id(
            linkedin_id="4123", company="Acme", title="AI Engineer", location="Warsaw"
        )
        assert got == "li:4123"

    def test_hash_is_stable_and_normalized(self):
        a = canonical_job_id(
            linkedin_id=None, company="Acme Inc.", title="AI Engineer", location="Warsaw"
        )
        b = canonical_job_id(
            linkedin_id=None, company="acme  inc", title="ai engineer", location="warsaw"
        )
        assert a == b, "one vacancy from two sources must collapse into one id"

    def test_different_jobs_differ(self):
        a = canonical_job_id(
            linkedin_id=None, company="Acme", title="AI Engineer", location="Warsaw"
        )
        b = canonical_job_id(
            linkedin_id=None, company="Acme", title="ML Engineer", location="Warsaw"
        )
        assert a != b

    def test_blank_linkedin_id_falls_back_to_hash(self):
        got = canonical_job_id(linkedin_id="   ", company="Acme", title="AI", location="Warsaw")
        assert got.startswith("h:")


class TestHardGate:
    def test_passes_for_matching_location(self, profile, config):
        assert check_hard_gate(_job(), profile, config) == []

    def test_remote_in_another_market_does_not_pass_location(self, profile, config):
        """Remote is not a free pass: a posting still hires in one market."""
        job = _job(location="Lisbon, Portugal", work_mode=WorkMode.REMOTE)
        failures = check_hard_gate(job, profile, config)
        assert len(failures) == 1 and "location" in failures[0]

    def test_remote_without_a_stated_market_passes_location(self, profile, config):
        job = _job(location="Remote", work_mode=WorkMode.REMOTE)
        assert check_hard_gate(job, profile, config) == []

    def test_wrong_location_fails(self, profile, config):
        job = _job(location="Berlin, Germany", work_mode=WorkMode.ONSITE)
        failures = check_hard_gate(job, profile, config)
        assert len(failures) == 1 and "location" in failures[0]

    def test_unknown_location_does_not_fail(self, profile, config):
        job = _job(location=None, work_mode=WorkMode.ONSITE)
        assert check_hard_gate(job, profile, config) == []

    def test_insufficient_years_fails(self, profile, config):
        job = _job(
            requirements=[
                Requirement(skill="Python", kind=RequirementKind.MUST_HAVE, years=12),
            ]
        )
        failures = check_hard_gate(job, profile, config)
        assert any("years of experience" in f for f in failures)

    def test_half_year_tolerance(self, profile, config):
        job = _job(
            requirements=[Requirement(skill="Python", kind=RequirementKind.MUST_HAVE, years=8.5)]
        )
        assert check_hard_gate(job, profile, config) == []

    def test_nice_to_have_years_ignored_by_gate(self, profile, config):
        job = _job(
            requirements=[
                Requirement(skill="Rust", kind=RequirementKind.NICE_TO_HAVE, years=20),
            ]
        )
        assert check_hard_gate(job, profile, config) == []

    def test_unknown_years_in_profile_does_not_fail(self, config):
        bare = CandidateProfile(user_id="t")
        job = _job(requirements=[Requirement(skill="Python", years=15)])
        assert check_hard_gate(job, bare, config) == []


class TestScoring:
    def test_evidence_is_required_for_a_point(self, profile, config):
        """A skill absent from the profile scores nothing and lands in the gaps."""
        job = _job(requirements=[Requirement(skill="Elixir", kind=RequirementKind.MUST_HAVE)])
        report = score_job(job, profile, config)
        assert report.breakdown["must_have_overlap"] == 0
        assert report.gaps == ["Elixir"]
        assert report.top_gap == "Elixir"

    def test_direct_match_cites_profile_line(self, profile, config):
        job = _job(requirements=[Requirement(skill="Python", kind=RequirementKind.MUST_HAVE)])
        report = score_job(job, profile, config)
        match = report.matches[0]
        assert match.matched and not match.transferable
        assert match.evidence == "8 years building backend services in Python"

    def test_transferable_match_is_discounted(self, profile, config):
        """LangGraph is missing but LangChain is there, so it counts at a discount."""
        job = _job(requirements=[Requirement(skill="LangGraph", kind=RequirementKind.MUST_HAVE)])
        report = score_job(job, profile, config)
        match = report.matches[0]
        assert match.matched and match.transferable
        assert report.breakdown["must_have_overlap"] == 0
        expected = config.scoring.weights.transferable * config.scoring.transferable_discount
        assert report.breakdown["transferable"] == pytest.approx(expected)

    def test_alias_matches_profile(self, profile, config):
        """K8s in a vacancy must find Kubernetes in the profile."""
        job = _job(requirements=[Requirement(skill="K8s", kind=RequirementKind.MUST_HAVE)])
        report = score_job(job, profile, config)
        assert report.matches[0].matched

    def test_full_match_scores_high_and_says_apply_now(self, profile, config):
        job = _job(
            requirements=[
                Requirement(skill="Python", kind=RequirementKind.MUST_HAVE),
                Requirement(skill="Kubernetes", kind=RequirementKind.MUST_HAVE),
            ],
            tech_stack=["Python", "Kubernetes"],
        )
        report = score_job(job, profile, config)
        assert report.score >= config.scoring.thresholds.apply_now
        assert report.verdict is FitVerdict.APPLY_NOW
        assert report.gaps == []

    def test_hard_gate_failure_caps_score(self, profile, config):
        """A perfect skill match must not rescue a vacancy in another country."""
        job = _job(
            location="Berlin, Germany",
            work_mode=WorkMode.ONSITE,
            requirements=[
                Requirement(skill="Python", kind=RequirementKind.MUST_HAVE),
                Requirement(skill="Kubernetes", kind=RequirementKind.MUST_HAVE),
            ],
            tech_stack=["Python", "Kubernetes"],
        )
        report = score_job(job, profile, config)
        assert not report.hard_gate_passed
        assert report.score <= config.scoring.hard_gate_fail_cap
        assert report.verdict is FitVerdict.SKIP

    def test_score_stays_in_range(self, profile, config):
        job = _job(
            requirements=[Requirement(skill=f"Skill{i}") for i in range(30)],
            tech_stack=[f"Skill{i}" for i in range(30)],
        )
        report = score_job(job, profile, config)
        assert 0 <= report.score <= 100

    def test_no_requirements_does_not_crash(self, profile, config):
        report = score_job(_job(), profile, config)
        assert 0 <= report.score <= 100
        assert report.gaps == []

    def test_scoring_is_deterministic(self, profile, config):
        job = _job(requirements=[Requirement(skill="Python"), Requirement(skill="Elixir")])
        first = score_job(job, profile, config)
        second = score_job(job, profile, config)
        assert first.model_dump() == second.model_dump()


class TestSeniorityFit:
    def test_exact_match(self, profile):
        assert seniority_fit(_job(seniority=Seniority.SENIOR), profile) == 1.0

    def test_adjacent_is_halved(self, profile):
        assert seniority_fit(_job(seniority=Seniority.STAFF), profile) == 0.5

    def test_far_is_zero(self, profile):
        assert seniority_fit(_job(seniority=Seniority.VP), profile) == 0.0

    def test_unknown_is_neutral(self, profile):
        assert seniority_fit(_job(seniority=Seniority.UNKNOWN), profile) == 1.0


class TestAggregateGaps:
    def test_ranks_by_frequency_and_skips_known(self, profile, config):
        jobs = [
            _job(
                canonical_id="a",
                requirements=[Requirement(skill="LangGraph"), Requirement(skill="Python")],
            ),
            _job(canonical_id="b", requirements=[Requirement(skill="LangGraph")]),
            _job(
                canonical_id="c",
                requirements=[Requirement(skill="LangGraph"), Requirement(skill="Terraform")],
            ),
        ]
        gaps = aggregate_gaps(jobs, profile, config)
        assert gaps[0][0] == "langgraph"
        assert gaps[0][1] == 3
        assert gaps[0][2] == 1.0
        assert all(skill != "python" for skill, _, _ in gaps), "a known skill is not a gap"

    def test_duplicate_skill_in_one_job_counted_once(self, profile, config):
        jobs = [
            _job(
                canonical_id="a",
                requirements=[Requirement(skill="Terraform"), Requirement(skill="terraform")],
            )
        ]
        gaps = aggregate_gaps(jobs, profile, config)
        assert gaps == [("terraform", 1, 1.0)]

    def test_empty_corpus(self, profile, config):
        assert aggregate_gaps([], profile, config) == []
