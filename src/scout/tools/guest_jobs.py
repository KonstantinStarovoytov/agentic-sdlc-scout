"""The LinkedIn guest jobs endpoint: a broad, cheap scan without authentication.

It answers without a cookie and never touches the burner account, which is why
it carries the bulk of the `scan` node. It returns only a card: title, company,
location and date. Full descriptions come through MCP, and only for vacancies
that survived the prefilter.

The network is not mocked for the sake of purity; parsing is separated from
fetching (`parse_job_cards`) so tests can run against recorded HTML.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import date, datetime
from urllib.parse import urlencode

import httpx
from selectolax.parser import HTMLParser, Node

from ..schemas import JobPosting, Seniority, WorkMode, canonical_job_id

logger = logging.getLogger(__name__)

GUEST_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# The guest endpoint returns 25 cards per page.
PAGE_SIZE = 25

_WORK_MODE_CODES = {"onsite": "1", "remote": "2", "hybrid": "3"}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

_JOB_URN = re.compile(r"urn:li:jobPosting:(\d+)")
_JOB_URL_ID = re.compile(r"/jobs/view/[^/]*?-(\d+)(?:\?|$)")

_SENIORITY_PATTERNS: list[tuple[re.Pattern[str], Seniority]] = [
    (re.compile(r"\b(intern|internship|praktyk)", re.I), Seniority.INTERN),
    (re.compile(r"\b(junior|jr\.?|entry[- ]level)\b", re.I), Seniority.JUNIOR),
    (re.compile(r"\b(principal)\b", re.I), Seniority.PRINCIPAL),
    (re.compile(r"\b(director)\b", re.I), Seniority.DIRECTOR),
    (re.compile(r"\b(vp|vice president|head of)\b", re.I), Seniority.VP),
    (re.compile(r"\b(staff)\b", re.I), Seniority.STAFF),
    (re.compile(r"\b(lead|leader)\b", re.I), Seniority.LEAD),
    (re.compile(r"\b(senior|sr\.?)\b", re.I), Seniority.SENIOR),
    (re.compile(r"\b(mid[- ]level|regular)\b", re.I), Seniority.MID),
]


def guess_seniority(title: str) -> Seniority:
    """Infer seniority from the title, for the prefilter.

    Pattern order is significant: "Senior Staff Engineer" must resolve to staff,
    so stronger levels are tested first.
    """
    for pattern, level in _SENIORITY_PATTERNS:
        if pattern.search(title):
            return level
    return Seniority.UNKNOWN


def _text(node: Node, selector: str) -> str | None:
    found = node.css_first(selector)
    if not found:
        return None
    value = found.text(strip=True)
    return value or None


def _extract_job_id(card: Node) -> str | None:
    urn = card.css_first("[data-entity-urn]")
    if urn:
        match = _JOB_URN.search(urn.attributes.get("data-entity-urn") or "")
        if match:
            return match.group(1)
    link = card.css_first("a.base-card__full-link, a[href*='/jobs/view/']")
    if link:
        match = _JOB_URL_ID.search(link.attributes.get("href") or "")
        if match:
            return match.group(1)
    return None


def _parse_posted_at(card: Node) -> date | None:
    node = card.css_first("time[datetime]")
    if not node:
        return None
    raw = node.attributes.get("datetime") or ""
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def parse_job_cards(html: str, *, work_mode: WorkMode = WorkMode.UNKNOWN) -> list[JobPosting]:
    """Parse an HTML fragment from the guest endpoint into cards.

    Deliberately separated from the network: this is the one fragile part —
    LinkedIn changes its markup — and it has to be testable against recorded HTML.
    """
    tree = HTMLParser(html)
    postings: list[JobPosting] = []

    for card in tree.css("li"):
        title = _text(card, "h3.base-search-card__title") or _text(card, "h3")
        company = _text(card, "h4.base-search-card__subtitle a") or _text(card, "h4")
        if not title or not company:
            continue

        location = _text(card, "span.job-search-card__location")
        job_id = _extract_job_id(card)
        link_node = card.css_first("a.base-card__full-link, a[href*='/jobs/view/']")
        href = link_node.attributes.get("href") if link_node else None
        url = href.split("?")[0] if href else None

        postings.append(
            JobPosting(
                canonical_id=canonical_job_id(
                    linkedin_id=job_id, company=company, title=title, location=location
                ),
                source="linkedin_guest",
                url=url,
                title=title,
                company=company,
                location=location,
                work_mode=work_mode,
                seniority=guess_seniority(title),
                posted_at=_parse_posted_at(card),
            )
        )

    return postings


class GuestJobsClient:
    """A client with jitter and backoff.

    The endpoint is public but not free in terms of LinkedIn's patience: without
    pauses it starts returning 429, and then the scan stops working entirely.
    """

    def __init__(
        self,
        *,
        min_delay: float = 1.0,
        max_delay: float = 3.0,
        max_retries: int = 3,
        timeout: float = 20.0,
    ) -> None:
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.timeout = timeout

    async def _fetch_page(self, client: httpx.AsyncClient, params: dict[str, str]) -> str | None:
        url = f"{GUEST_SEARCH_URL}?{urlencode(params)}"
        for attempt in range(self.max_retries):
            try:
                response = await client.get(url, headers=_HEADERS, timeout=self.timeout)
            except httpx.HTTPError:
                await asyncio.sleep(2**attempt)
                continue

            if response.status_code == 200:
                return response.text
            if response.status_code in (429, 503):
                await asyncio.sleep((2**attempt) * 2 + random.uniform(0, 1))  # noqa: S311
                continue
            # A 400 on a large `start` means the end of the results, not a fault.
            return None
        return None

    async def search(
        self,
        *,
        keywords: str,
        location: str,
        freshness_days: int = 30,
        work_mode: str | None = None,
        limit: int = 25,
    ) -> list[JobPosting]:
        """Page through the endpoint until `limit` distinct cards are collected."""
        params_base: dict[str, str] = {
            "keywords": keywords,
            "location": location,
            "f_TPR": f"r{freshness_days * 86400}",
        }
        mode_code = _WORK_MODE_CODES.get((work_mode or "").lower())
        if mode_code:
            params_base["f_WT"] = mode_code
        resolved_mode = (
            WorkMode(work_mode.lower())
            if work_mode and work_mode.lower() in WorkMode._value2member_map_
            else WorkMode.UNKNOWN
        )

        results: list[JobPosting] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(follow_redirects=True) as client:
            start = 0
            while len(results) < limit:
                params = {**params_base, "start": str(start)}
                html = await self._fetch_page(client, params)
                if not html:
                    break

                page = parse_job_cards(html, work_mode=resolved_mode)
                if not page:
                    break

                for job in page:
                    if job.canonical_id in seen:
                        continue
                    seen.add(job.canonical_id)
                    results.append(job)
                    if len(results) >= limit:
                        break

                start += PAGE_SIZE
                await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))  # noqa: S311

        return results


async def scan_guest_jobs(
    *,
    roles: list[str],
    locations: list[str],
    freshness_days: int = 30,
    max_results_per_role: int = 25,
    work_modes: list[str] | None = None,
) -> list[JobPosting]:
    """Scan every role and location, deduplicating by canonical key."""
    client = GuestJobsClient()
    collected: dict[str, JobPosting] = {}

    for role in roles:
        for location in locations:
            modes: list[str | None] = list(work_modes) if work_modes else [None]
            for mode in modes:
                try:
                    found = await client.search(
                        keywords=role,
                        location=location,
                        freshness_days=freshness_days,
                        work_mode=mode,
                        limit=max_results_per_role,
                    )
                except Exception as exc:
                    # A partial result beats a crash: one broken role/location
                    # combination must not take the whole scan down.
                    logger.info("Scan failed for %s / %s: %s", role, location, exc)
                    continue
                for job in found:
                    collected.setdefault(job.canonical_id, job)

    return list(collected.values())
