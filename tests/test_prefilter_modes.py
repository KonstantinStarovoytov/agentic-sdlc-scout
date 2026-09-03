"""Work modes, from the config through the scan and into the hard gate.

`search.remote_modes` was loaded and then dropped on the floor, so LinkedIn's
`f_WT` filter never went out and every posting came back with an unknown work
mode. The location gate answered that by waving remote work through, which,
once the mode is actually populated, would let a third of the corpus past the
only geographic check there is.
"""

from __future__ import annotations

import pytest

from scout.config import ScoutConfig
from scout.graphs.research import scan_node
from scout.schemas import JobPosting, Seniority, WorkMode
from scout.scoring import check_hard_gate, location_matches
from scout.tools import guest_jobs


@pytest.fixture
def config() -> ScoutConfig:
    cfg = ScoutConfig()
    cfg.search.roles = ["AI Engineer"]
    cfg.search.locations = ["Warsaw, Mazowieckie, Poland", "Poland"]
    cfg.search.remote_modes = ["onsite", "remote", "hybrid"]
    return cfg


@pytest.fixture
def recorded_scan(monkeypatch, config):
    """Replace the network scan with a recorder and pin the config it reads."""
    calls: list[dict] = []

    async def fake_scan(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr("scout.graphs.research.get_config", lambda: config)
    monkeypatch.setattr("scout.graphs.research.scan_guest_jobs", fake_scan)
    return calls


class TestScanUsesConfiguredModes:
    async def test_configured_modes_reach_the_scan(self, recorded_scan):
        await scan_node({}, None)
        assert recorded_scan[0]["work_modes"] == ["onsite", "remote", "hybrid"]

    async def test_an_empty_list_means_no_filter_rather_than_no_results(
        self, recorded_scan, config
    ):
        """An unset config must not turn into a search for the empty work mode."""
        config.search.remote_modes = []
        await scan_node({}, None)
        assert recorded_scan[0]["work_modes"] is None


class TestGuestScanFansOutOverModes:
    async def test_one_search_per_role_location_mode(self, monkeypatch):
        seen: list[tuple[str, str, str | None]] = []

        async def fake_search(self, *, keywords, location, work_mode=None, **kwargs):
            seen.append((keywords, location, work_mode))
            return []

        monkeypatch.setattr(guest_jobs.GuestJobsClient, "search", fake_search)
        await guest_jobs.scan_guest_jobs(
            roles=["AI Engineer"],
            locations=["Poland"],
            work_modes=["remote", "hybrid"],
        )
        assert seen == [
            ("AI Engineer", "Poland", "remote"),
            ("AI Engineer", "Poland", "hybrid"),
        ]

    async def test_no_modes_means_a_single_unfiltered_pass(self, monkeypatch):
        seen: list[str | None] = []

        async def fake_search(self, *, work_mode=None, **kwargs):
            seen.append(work_mode)
            return []

        monkeypatch.setattr(guest_jobs.GuestJobsClient, "search", fake_search)
        await guest_jobs.scan_guest_jobs(roles=["AI Engineer"], locations=["Poland"])
        assert seen == [None]


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


ALLOWED = ["Warsaw, Mazowieckie, Poland", "Poland"]


class TestLocationGate:
    def test_matching_location_passes(self):
        assert location_matches(_job(), ALLOWED)

    def test_remote_in_the_target_market_passes(self):
        job = _job(location="Krakow, Poland", work_mode=WorkMode.REMOTE)
        assert location_matches(job, ALLOWED)

    def test_remote_in_another_market_is_not_waved_through(self):
        """The defect: "remote" used to be a blanket pass regardless of country."""
        job = _job(location="San Francisco, California, United States", work_mode=WorkMode.REMOTE)
        assert not location_matches(job, ALLOWED)

    @pytest.mark.parametrize(
        "location", ["Remote", "Worldwide", "Anywhere", "European Union", "EMEA"]
    )
    def test_remote_without_a_real_market_gets_the_benefit_of_the_doubt(self, location):
        """These name no market the gate could check, so they are not a failure."""
        assert location_matches(_job(location=location, work_mode=WorkMode.REMOTE), ALLOWED)

    def test_an_onsite_job_in_a_region_name_is_still_checked(self):
        """Only remote earns the relaxation; "onsite in the EU" is not a place."""
        assert not location_matches(_job(location="EMEA", work_mode=WorkMode.ONSITE), ALLOWED)

    def test_unknown_location_is_not_punished(self):
        assert location_matches(_job(location=None, work_mode=WorkMode.ONSITE), ALLOWED)

    def test_no_configured_locations_means_nothing_to_check(self):
        assert location_matches(_job(location="Berlin, Germany"), [])


class TestGateReporting:
    def test_the_failure_names_the_work_mode(self, config):
        """A capped remote vacancy is the one the user will want to argue with."""
        profile_config = config
        job = _job(location="Berlin, Germany", work_mode=WorkMode.REMOTE)
        from scout.schemas import CandidateProfile

        failures = check_hard_gate(job, CandidateProfile(user_id="owner"), profile_config)
        assert len(failures) == 1
        assert "remote" in failures[0] and "Berlin" in failures[0]
