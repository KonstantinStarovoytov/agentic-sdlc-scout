"""Applying the rubric and running the aggregate gap analysis.

The numbers come from `scoring.py`, deterministically and without a model. These
tools are only the bridge between memory and the rubric: fetch the vacancies and
the profile, compute, return a compact table. Explaining the numbers in human
language is the agent's job.
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool
from langgraph.store.base import BaseStore

from ..config import get_config, get_settings
from ..memory import jobs_ns, load_feedback, profile_ns, save_feedback
from ..schemas import CandidateProfile, JobPosting
from ..scoring import aggregate_gaps, score_job

logger = logging.getLogger(__name__)

_VERDICT_LABEL = {
    "apply_now": "apply now",
    "apply_after_gap": "apply after closing the gap",
    "skip": "skip",
}


def _store() -> BaseStore | None:
    try:
        from langgraph.config import get_store

        return get_store()
    except Exception:
        return None


async def _load_profile(store: BaseStore, user_id: str) -> CandidateProfile | None:
    item = await store.aget(profile_ns(user_id), "current")
    if item is None:
        return None
    try:
        return CandidateProfile.model_validate(item.value)
    except Exception as exc:
        logger.warning("Stored profile is corrupt: %s", exc)
        return None


async def _load_jobs(store: BaseStore, user_id: str, job_ids: list[str] | None) -> list[JobPosting]:
    namespace = jobs_ns(user_id)
    jobs: list[JobPosting] = []

    if job_ids:
        for job_id in job_ids:
            item = await store.aget(namespace, job_id)
            if item is not None:
                jobs.append(JobPosting.model_validate(item.value))
        return jobs

    for item in await store.asearch(namespace, limit=200):
        try:
            jobs.append(JobPosting.model_validate(item.value))
        except Exception as exc:
            logger.debug("Skipping unreadable stored vacancy %s: %s", item.key, exc)
    return jobs


@tool
async def score_jobs(job_ids: list[str] | None = None) -> str:
    """Score how well the profile fits vacancies, using the deterministic rubric.

    Every match is backed by a quote from the Candidate Profile; a skill without
    a quote scores nothing. Failing the hard gate caps the score from above.

    Args:
        job_ids: canonical vacancy ids. Empty means every known vacancy.

    Returns:
        A markdown table of scores and verdicts, plus quoted evidence for the top matches.
    """
    settings = get_settings()
    config = get_config()
    store = _store()
    if store is None:
        return "Memory is unavailable; there is nothing to score."

    profile = await _load_profile(store, settings.scout_user_id)
    if profile is None:
        return (
            "The Candidate Profile has not been assembled. Run bootstrap_profile — "
            "without a profile the score would be invention rather than assessment."
        )

    jobs = await _load_jobs(store, settings.scout_user_id, job_ids)
    if not jobs:
        return "There are no vacancies in memory. Run research_jobs first."

    reports = [(job, score_job(job, profile, config)) for job in jobs]
    reports.sort(key=lambda pair: pair[1].score, reverse=True)

    lines = ["| Role | Company | Score | Verdict | Main gap |", "|---|---|---|---|---|"]
    for job, report in reports:
        gap = report.top_gap or "-"
        if not report.hard_gate_passed:
            gap = f"gate: {report.hard_gate_failures[0]}"
        lines.append(
            f"| {job.title} | {job.company} | {report.score} | "
            f"{_VERDICT_LABEL[report.verdict.value]} | {gap} |"
        )

    evidence: list[str] = []
    for job, report in reports[:3]:
        proofs = [
            f'  - {m.skill}: "{m.evidence}"' for m in report.matches if m.matched and m.evidence
        ][:4]
        if proofs:
            evidence.append(f"- {job.title} ({job.company}):\n" + "\n".join(proofs))

    result = "\n".join(lines)
    if evidence:
        result += "\n\nEvidence for the matches (quoted from the profile):\n" + "\n".join(evidence)
    return result


@tool
async def gap_analysis() -> str:
    """Aggregate the gaps across the whole corpus of vacancies.

    Answers "what should I learn this month" rather than "where do I apply
    today": which mandatory requirements appear most often and are missing from
    the profile.

    Returns:
        A ranked list of missing skills with how many postings demand each.
    """
    settings = get_settings()
    store = _store()
    if store is None:
        return "Memory is unavailable."

    profile = await _load_profile(store, settings.scout_user_id)
    if profile is None:
        return "The Candidate Profile has not been assembled. Run bootstrap_profile."

    jobs = await _load_jobs(store, settings.scout_user_id, None)
    if not jobs:
        return "There are no vacancies in memory. Run research_jobs first."

    gaps = aggregate_gaps(jobs, profile)
    if not gaps:
        return f"Across {len(jobs)} vacancies, no gaps in mandatory requirements were found."

    lines = [f"Corpus: {len(jobs)} vacancies. What is missing, by how often it is demanded:"]
    lines += [
        f"{i}. {skill} - in {count} of {len(jobs)} ({share * 100:.0f}%)"
        for i, (skill, count, share) in enumerate(gaps[:12], start=1)
    ]
    return "\n".join(lines)


@tool
async def remember_preference(note: str, company_to_avoid: str | None = None) -> str:
    """Remember the user's reaction to vacancies.

    "Too senior", "not this company" — this changes the prefilter and the scoring
    of later runs. Without it the agent brings back the same junk every time.

    Args:
        note: the preference in the user's own words.
        company_to_avoid: a company that should no longer be shown.

    Returns:
        Confirmation with the number of stored preferences and blocked companies.
    """
    settings = get_settings()
    store = _store()
    if store is None:
        return "Memory is unavailable; the preference was not saved."

    data = await load_feedback(store, settings.scout_user_id)
    notes = list(data.get("notes", []))
    denied = list(data.get("company_deny", []))

    if note and note not in notes:
        notes.append(note)
    if company_to_avoid and company_to_avoid not in denied:
        denied.append(company_to_avoid)

    await save_feedback(store, settings.scout_user_id, {"notes": notes, "company_deny": denied})
    return f"Noted. Stored preferences: {len(notes)}, companies on the stop-list: {len(denied)}."
