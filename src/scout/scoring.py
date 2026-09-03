"""The deterministic half of the fit-score rubric.

No LLM is involved here: everything is computed from data and covered by unit
tests. The model is only responsible for the qualitative part — wording and
explanation — layered on top of numbers that are already fixed.

The governing rule: a skill scores only when the profile contains a claim with
evidence. No quote, no point. That is what stops the rubric from inflating a
vacancy into a flattering number.
"""

from __future__ import annotations

from .config import ScoutConfig, get_config
from .schemas import (
    CandidateProfile,
    FitReport,
    FitVerdict,
    JobPosting,
    RequirementKind,
    Seniority,
    SkillMatch,
    WorkMode,
    normalize_skill,
)

# Skill adjacency: the key counts as transferable when the profile holds any of
# the values. The discount factor comes from the config.
TRANSFERABLE: dict[str, set[str]] = {
    "langgraph": {"langchain", "large language models", "python"},
    "langchain": {"langgraph", "large language models", "python"},
    "retrieval augmented generation": {
        "large language models",
        "elasticsearch",
        "vector databases",
    },
    "model context protocol": {"large language models", "langchain", "api design"},
    "vector databases": {"postgresql", "elasticsearch", "redis"},
    "kubernetes": {"docker", "terraform", "amazon web services"},
    "terraform": {"kubernetes", "amazon web services", "google cloud platform"},
    "amazon web services": {"google cloud platform", "azure", "kubernetes"},
    "google cloud platform": {"amazon web services", "azure", "kubernetes"},
    "typescript": {"javascript"},
    "go": {"python", "java", "rust"},
    "mlops": {"ci/cd", "kubernetes", "machine learning"},
    "prompt engineering": {"large language models"},
    "evals": {"large language models", "testing"},
}

# Seniority order, used for "higher/lower" comparisons.
_SENIORITY_RANK: dict[Seniority, int] = {
    Seniority.INTERN: 0,
    Seniority.JUNIOR: 1,
    Seniority.MID: 2,
    Seniority.SENIOR: 3,
    Seniority.STAFF: 4,
    Seniority.LEAD: 4,
    Seniority.PRINCIPAL: 5,
    Seniority.DIRECTOR: 6,
    Seniority.VP: 7,
}


# Location strings that pin a remote posting to no particular national market,
# or to one wider than the tracked EU search. Deliberately short: anything more
# precise needs real geography, and a wrong guess here caps a score at
# `hard_gate_fail_cap` on a vacancy the user could actually take.
_UNBOUNDED_LOCATIONS = {
    "remote",
    "fully remote",
    "anywhere",
    "worldwide",
    "global",
    "europe",
    "eu",
    "european union",
    "eea",
    "european economic area",
    "emea",
}


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {t for t in normalize_skill(value).split() if t}


def _is_unbounded_location(value: str) -> bool:
    """Whether a location string names no market the gate could check against."""
    return normalize_skill(value) in _UNBOUNDED_LOCATIONS


def location_matches(job: JobPosting, allowed_locations: list[str]) -> bool:
    """Check the posting's location against the configured ones.

    Being remote is not a free pass. A remote posting still carries the market it
    hires in, and "remote, but only within the United States" is a real reason
    the user cannot take the job. What remote does buy is the benefit of the
    doubt when the stated location names no enforceable market at all.
    """
    if not allowed_locations:
        return True
    if not job.location:
        # The scan queries one configured location at a time, so a blank field is
        # missing data rather than evidence of the wrong market.
        return True
    if job.work_mode is WorkMode.REMOTE and _is_unbounded_location(job.location):
        return True
    job_tokens = _tokens(job.location)
    if not job_tokens:
        return True
    return any(_tokens(loc) & job_tokens for loc in allowed_locations)


def required_years(job: JobPosting) -> float | None:
    """Return the largest number of years demanded by a must-have requirement."""
    values = [r.years for r in job.requirements if r.kind is RequirementKind.MUST_HAVE and r.years]
    return max(values) if values else None


def check_hard_gate(job: JobPosting, profile: CandidateProfile, config: ScoutConfig) -> list[str]:
    """Return the list of gate failures; an empty list means the gate passed.

    Only genuinely known facts are checked. Unknown is not a failure: letting a
    vacancy through is more honest than rejecting it on a guess.
    """
    failures: list[str] = []

    if not location_matches(job, config.search.locations):
        # The work mode is named because a capped remote vacancy is the case the
        # user is most likely to want to argue with.
        failures.append(
            f"location: {job.location} ({job.work_mode.value}) outside {config.search.locations}"
        )

    if job.visa_sponsorship is False and not profile.work_authorization:
        failures.append("no visa sponsorship, and the profile states no right to work")

    needed = required_years(job)
    if (
        needed is not None
        and profile.years_experience is not None
        and profile.years_experience + 0.5 < needed
    ):
        failures.append(
            f"requires {needed:g} years of experience, profile has {profile.years_experience:g}"
        )

    if job.language and profile.languages:
        known = {normalize_skill(x) for x in profile.languages}
        if normalize_skill(job.language) not in known:
            failures.append(f"posting language {job.language} is not listed in the profile")

    return failures


def match_requirements(
    job: JobPosting, profile: CandidateProfile
) -> tuple[list[SkillMatch], list[str]]:
    """Match requirements against the profile. A point requires evidence."""
    matches: list[SkillMatch] = []
    gaps: list[str] = []
    profile_skills = profile.skills()

    for req in job.requirements:
        claim = profile.find_claim(req.skill)
        if claim is not None:
            matches.append(SkillMatch(skill=req.skill, matched=True, evidence=claim.evidence))
            continue

        adjacent = TRANSFERABLE.get(normalize_skill(req.skill), set())
        bridge = next((s for s in adjacent if s in profile_skills), None)
        if bridge is not None:
            bridge_claim = profile.find_claim(bridge)
            matches.append(
                SkillMatch(
                    skill=req.skill,
                    matched=True,
                    evidence=bridge_claim.evidence if bridge_claim else None,
                    transferable=True,
                )
            )
            continue

        matches.append(SkillMatch(skill=req.skill, matched=False))
        if req.kind is RequirementKind.MUST_HAVE:
            gaps.append(req.skill)

    return matches, gaps


def seniority_fit(job: JobPosting, profile: CandidateProfile) -> float:
    """Return 1.0 for a direct hit, 0.5 for an adjacent level, 0.0 for far off."""
    if job.seniority is Seniority.UNKNOWN:
        return 1.0
    job_rank = _SENIORITY_RANK.get(job.seniority)
    if job_rank is None:
        return 1.0

    years = profile.years_experience
    if years is None:
        return 1.0
    if years < 2:
        own = 1
    elif years < 5:
        own = 2
    elif years < 9:
        own = 3
    elif years < 13:
        own = 4
    else:
        own = 5

    distance = abs(job_rank - own)
    if distance == 0:
        return 1.0
    if distance == 1:
        return 0.5
    return 0.0


def score_job(
    job: JobPosting,
    profile: CandidateProfile,
    config: ScoutConfig | None = None,
) -> FitReport:
    """Compute the fit score and verdict. Fully deterministic."""
    cfg = config or get_config()
    weights = cfg.scoring.weights

    failures = check_hard_gate(job, profile, cfg)
    matches, gaps = match_requirements(job, profile)

    must_haves = [r for r in job.requirements if r.kind is RequirementKind.MUST_HAVE]
    must_names = {normalize_skill(r.skill) for r in must_haves}
    must_matches = [m for m in matches if normalize_skill(m.skill) in must_names]

    direct = sum(1 for m in must_matches if m.matched and not m.transferable)
    bridged = sum(1 for m in must_matches if m.matched and m.transferable)
    total_must = len(must_haves)

    if total_must:
        overlap_fraction = direct / total_must
        transferable_fraction = (bridged / total_must) * cfg.scoring.transferable_discount
    else:
        # No requirements were extracted: neither punish nor reward.
        overlap_fraction = 0.0
        transferable_fraction = 0.0

    stack = [normalize_skill(s) for s in job.tech_stack]
    profile_skills = profile.skills()
    signal_fraction = sum(1 for s in stack if s in profile_skills) / len(stack) if stack else 0.0

    sen_fraction = seniority_fit(job, profile)

    breakdown = {
        "must_have_overlap": round(weights.must_have_overlap * overlap_fraction, 2),
        "transferable": round(weights.transferable * transferable_fraction, 2),
        "signals": round(weights.signals * signal_fraction, 2),
        "seniority_fit": round(weights.seniority_fit * sen_fraction, 2),
    }
    raw_score = round(sum(breakdown.values()))
    raw_score = max(0, min(100, raw_score))

    gate_passed = not failures
    score = raw_score if gate_passed else min(raw_score, cfg.scoring.hard_gate_fail_cap)

    thresholds = cfg.scoring.thresholds
    if score >= thresholds.apply_now:
        verdict = FitVerdict.APPLY_NOW
    elif score >= thresholds.apply_after_gap:
        verdict = FitVerdict.APPLY_AFTER_GAP
    else:
        verdict = FitVerdict.SKIP

    return FitReport(
        canonical_id=job.canonical_id,
        score=score,
        verdict=verdict,
        hard_gate_passed=gate_passed,
        hard_gate_failures=failures,
        matches=matches,
        gaps=gaps,
        top_gap=gaps[0] if gaps else None,
        breakdown=breakdown,
    )


def aggregate_gaps(
    jobs: list[JobPosting],
    profile: CandidateProfile,
    config: ScoutConfig | None = None,
) -> list[tuple[str, int, float]]:
    """Aggregate gap analysis across the whole corpus of vacancies.

    Answers "what should I learn this month" rather than "where do I apply
    today": returns skills absent from the profile, ranked by how often they are
    demanded. Each entry is (skill, number of postings demanding it, share).

    `config` is unused today but keeps the signature uniform with the rest of the
    module, which callers rely on.
    """
    if not jobs:
        return []

    profile_skills = profile.skills()
    counter: dict[str, int] = {}
    for job in jobs:
        seen: set[str] = set()
        for req in job.requirements:
            if req.kind is not RequirementKind.MUST_HAVE:
                continue
            key = normalize_skill(req.skill)
            if key in profile_skills or key in seen:
                continue
            seen.add(key)
            counter[key] = counter.get(key, 0) + 1

    total = len(jobs)
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [(skill, count, round(count / total, 3)) for skill, count in ranked]
