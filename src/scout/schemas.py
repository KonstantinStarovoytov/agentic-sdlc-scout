"""Data schemas for the agent.

Two principles carry the honesty of the whole system:

1. Every statement about the user (`ProfileClaim`) stores its source. The scoring
   rubric must quote a specific line from the profile rather than assert a
   general "looks like a fit".
2. `JobCard` is the compact card, and it is the only thing that reaches the
   agent's context. The full `JobPosting` lives in the Store and is read by a
   subagent only when genuinely needed. Without that split the context burns out
   around the fifth vacancy.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Seniority(StrEnum):
    """Seniority levels, ordered from least to most senior."""

    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    LEAD = "lead"
    PRINCIPAL = "principal"
    DIRECTOR = "director"
    VP = "vp"
    UNKNOWN = "unknown"


class WorkMode(StrEnum):
    """Where the work happens."""

    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class RequirementKind(StrEnum):
    """Whether a requirement is mandatory or merely desirable."""

    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"


class Requirement(BaseModel):
    """A single requirement taken from a job description."""

    skill: str = Field(description="Normalised skill or technology name")
    kind: RequirementKind = RequirementKind.MUST_HAVE
    years: float | None = Field(default=None, description="Years of experience, if stated")
    raw: str | None = Field(default=None, description="Original wording from the posting")


class JobPosting(BaseModel):
    """A full job dossier. Never enters the agent's context in one piece."""

    canonical_id: str = Field(description="LinkedIn job id, or a hash of company+title+location")
    source: Literal["linkedin_guest", "linkedin_mcp", "tavily", "manual"] = "linkedin_guest"
    url: str | None = None

    title: str
    company: str
    location: str | None = None
    work_mode: WorkMode = WorkMode.UNKNOWN
    seniority: Seniority = Seniority.UNKNOWN

    posted_at: date | None = None
    scanned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    description: str | None = Field(default=None, description="Raw description, Store only")
    requirements: list[Requirement] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)

    salary_raw: str | None = None
    language: str | None = Field(default=None, description="Posting language, ISO-639-1")
    visa_sponsorship: bool | None = None

    def card(self) -> JobCard:
        """Reduce the dossier to the few lines the agent is allowed to see."""
        return JobCard(
            canonical_id=self.canonical_id,
            title=self.title,
            company=self.company,
            location=self.location,
            work_mode=self.work_mode,
            seniority=self.seniority,
            url=self.url,
            posted_at=self.posted_at,
            must_have_count=sum(
                1 for r in self.requirements if r.kind is RequirementKind.MUST_HAVE
            ),
        )


class JobCard(BaseModel):
    """The handful of lines the agent actually sees."""

    canonical_id: str
    title: str
    company: str
    location: str | None = None
    work_mode: WorkMode = WorkMode.UNKNOWN
    seniority: Seniority = Seniority.UNKNOWN
    url: str | None = None
    posted_at: date | None = None
    must_have_count: int = 0


class ExtractedRequirements(BaseModel):
    """Structured-output schema for the extract node, which runs without tools."""

    requirements: list[Requirement] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    seniority: Seniority = Seniority.UNKNOWN
    work_mode: WorkMode = WorkMode.UNKNOWN
    salary_raw: str | None = None
    visa_sponsorship: bool | None = None
    language: str | None = None


class ProfileClaim(BaseModel):
    """A statement about the user together with its source.

    The source is mandatory: the rubric quotes it, and the ban on inventing
    experience is enforced by the fact that every skill has a visible origin.
    """

    skill: str
    evidence: str = Field(description="Verbatim line that backs the skill")
    source: Literal["cv", "linkedin", "site", "user_answer"] = "cv"
    years: float | None = None
    last_used: int | None = Field(default=None, description="Year the skill was last used")


class CandidateProfile(BaseModel):
    """The source of truth about the user. What is absent here is absent from the CV."""

    user_id: str
    full_name: str | None = None
    headline: str | None = None
    location: str | None = None
    years_experience: float | None = None

    claims: list[ProfileClaim] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)

    work_authorization: str | None = Field(default=None, description="For example: EU citizen")
    languages: list[str] = Field(default_factory=list)
    open_to_relocation: bool | None = None
    salary_expectation: str | None = None

    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def skills(self) -> set[str]:
        """Return the normalised set of skills backed by evidence."""
        return {normalize_skill(c.skill) for c in self.claims}

    def find_claim(self, skill: str) -> ProfileClaim | None:
        """Find the claim backing a skill, comparing in normalised form."""
        target = normalize_skill(skill)
        for claim in self.claims:
            if normalize_skill(claim.skill) == target:
                return claim
        return None


class SkillMatch(BaseModel):
    """One requirement checked against the profile."""

    skill: str
    matched: bool
    evidence: str | None = Field(default=None, description="Quote from the profile, else None")
    transferable: bool = False


class FitVerdict(StrEnum):
    """The three answers the rubric is allowed to give."""

    APPLY_NOW = "apply_now"
    APPLY_AFTER_GAP = "apply_after_gap"
    SKIP = "skip"


class FitReport(BaseModel):
    """Rubric output. The deterministic part is computed in `scoring.py`."""

    canonical_id: str
    score: int = Field(ge=0, le=100)
    verdict: FitVerdict

    hard_gate_passed: bool = True
    hard_gate_failures: list[str] = Field(default_factory=list)

    matches: list[SkillMatch] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    top_gap: str | None = None

    breakdown: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None


class SkillDemand(BaseModel):
    """How often one skill is demanded across the scanned corpus."""

    skill: str
    count: int
    share: float
    tier: Literal["core", "peripheral", "signal"]
    in_profile: bool = False


class Taxonomy(BaseModel):
    """A living record of what the track demands. Feeds prompt, scoring and gap analysis."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sample_size: int = 0
    demands: list[SkillDemand] = Field(default_factory=list)

    def core_skills(self) -> list[str]:
        """Return the skills demanded by most postings in the corpus."""
        return [d.skill for d in self.demands if d.tier == "core"]


# For skills the dot, plus and hash are meaningful: node.js, c++, c#.
_NON_ALNUM = re.compile(r"[^a-z0-9+#.]+")
# For company and job titles they are noise instead: "Acme Inc." and "Acme Inc"
# must produce the same key, otherwise cross-source dedup silently fails.
_NON_ALNUM_STRICT = re.compile(r"[^a-z0-9]+")

# Different spellings of the same thing. Without this skill dedup breaks and gap
# analysis reports "k8s" and "kubernetes" as two separate gaps.
_SKILL_ALIASES = {
    "k8s": "kubernetes",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "postgres": "postgresql",
    "gcp": "google cloud platform",
    "aws": "amazon web services",
    "llm": "large language models",
    "llms": "large language models",
    "rag": "retrieval augmented generation",
    "mcp": "model context protocol",
    "ci cd": "ci/cd",
    "cicd": "ci/cd",
}


def normalize_skill(value: str) -> str:
    """Reduce a skill to its canonical form for comparison and dedup."""
    cleaned = _NON_ALNUM.sub(" ", value.strip().lower()).strip()
    return _SKILL_ALIASES.get(cleaned, cleaned)


def canonical_job_id(
    *, linkedin_id: str | None, company: str, title: str, location: str | None
) -> str:
    """Return the LinkedIn job id, or a hash of the normalised triple when absent.

    A stable key is required: the same vacancy found through the guest endpoint
    and through Tavily has to collapse into one record before tokens are spent.
    """
    if linkedin_id and linkedin_id.strip():
        return f"li:{linkedin_id.strip()}"
    parts = [
        " ".join(_NON_ALNUM_STRICT.sub(" ", (value or "").lower()).split())
        for value in (company, title, location)
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"h:{digest}"
