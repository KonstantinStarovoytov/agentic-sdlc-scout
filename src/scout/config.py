"""Settings from the environment and from `config/search.yaml`.

Secrets live only in `.env`, search parameters only in the YAML. The code holds
neither: filters and weights will have to be calibrated against real results,
and that must never require editing Python.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "search.yaml"


class Settings(BaseSettings):
    """Secrets and connections. Everything is optional so the agent can start degraded."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = None
    tavily_api_key: str | None = None

    scout_model_fast: str = "openai:gpt-4.1-mini"
    scout_model_smart: str = "openai:gpt-4.1"

    # Empty means an in-memory store: development is possible without Neon.
    scout_database_url: str | None = None

    # Empty means LinkedIn tools are not attached; the guest source and Tavily carry the run.
    # There is no cookie setting to go with it: since server 4.x the session is a
    # stored browser profile under ~/.linkedin-mcp/, created by `--login`, and no
    # li_at cookie is accepted through the environment or the command line.
    scout_linkedin_mcp_command: str | None = None

    scout_user_id: str = "owner"
    scout_linkedin_profile_url: str | None = None
    scout_personal_site_url: str | None = None

    @property
    def has_postgres(self) -> bool:
        """Whether a Postgres connection string is configured."""
        return bool(self.scout_database_url and self.scout_database_url.strip())

    @property
    def has_linkedin(self) -> bool:
        """Whether the LinkedIn MCP server is configured."""
        return bool(self.scout_linkedin_mcp_command and self.scout_linkedin_mcp_command.strip())

    @property
    def has_tavily(self) -> bool:
        """Whether a Tavily API key is available."""
        return bool(self.tavily_api_key and self.tavily_api_key.strip())


class SearchConfig(BaseModel):
    """What to search for and where."""

    roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote_modes: list[str] = Field(default_factory=list)
    freshness_days: int = 30
    max_results_per_role: int = 25


class FiltersConfig(BaseModel):
    """Cheap prefilter rules applied before any LinkedIn request is spent."""

    seniority_allow: list[str] = Field(default_factory=list)
    seniority_deny: list[str] = Field(default_factory=list)
    company_deny: list[str] = Field(default_factory=list)
    title_deny_keywords: list[str] = Field(default_factory=list)


class BudgetsConfig(BaseModel):
    """Hard ceilings on cost and on how often LinkedIn is touched."""

    linkedin_calls_per_run: int = 15
    linkedin_calls_per_hour: int = 40
    linkedin_min_delay_seconds: float = 3.0
    linkedin_max_delay_seconds: float = 8.0
    max_tokens_per_run: int = 400_000
    max_tool_calls_per_run: int = 120
    tavily_calls_per_run: int = 20


class ScoringWeights(BaseModel):
    """Weights of the four rubric components; they should add up to 100."""

    must_have_overlap: int = 55
    transferable: int = 20
    signals: int = 15
    seniority_fit: int = 10

    def total(self) -> int:
        """Sum of all weights, for validating a hand-edited config."""
        return self.must_have_overlap + self.transferable + self.signals + self.seniority_fit


class ScoringThresholds(BaseModel):
    """Score boundaries between the three verdicts."""

    apply_now: int = 70
    apply_after_gap: int = 45


class ScoringConfig(BaseModel):
    """Everything the rubric needs that is worth calibrating later."""

    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    transferable_discount: float = 0.5
    hard_gate_fail_cap: int = 39
    thresholds: ScoringThresholds = Field(default_factory=ScoringThresholds)


class ProfileConfig(BaseModel):
    """Where the owner's source CV lives."""

    cv_path: str = "data/private/cv.pdf"


class TaxonomyConfig(BaseModel):
    """How the track taxonomy is built from a corpus of postings."""

    bootstrap_target: int = 40
    core_threshold: float = 0.5
    peripheral_threshold: float = 0.2


class ScoutConfig(BaseModel):
    """The full contents of `config/search.yaml`."""

    search: SearchConfig = Field(default_factory=SearchConfig)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    budgets: BudgetsConfig = Field(default_factory=BudgetsConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    profile: ProfileConfig = Field(default_factory=ProfileConfig)
    taxonomy: TaxonomyConfig = Field(default_factory=TaxonomyConfig)


def load_config(path: Path | str | None = None) -> ScoutConfig:
    """Read `search.yaml`. A missing file is not an error: schema defaults apply."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return ScoutConfig()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return ScoutConfig.model_validate(raw)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return process-wide settings, read once."""
    return Settings()


@lru_cache(maxsize=1)
def get_config() -> ScoutConfig:
    """Return the process-wide search configuration, read once."""
    return load_config()
