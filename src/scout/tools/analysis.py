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

from ..config import get_config
from ..identity import current_identity, current_user_id
from ..memory import jobs_ns, load_feedback, profile_ns, save_feedback, search_all
from ..schemas import CandidateProfile, JobPosting, RequirementKind
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

    # The whole corpus, paged. This was a single `asearch(limit=200)`, which was
    # everything until the corpus grew past it — after which list_known_jobs
    # reported "none of the 200 vacancies match" while the five target postings
    # sat in memory as items 201 to 445.
    for item in await search_all(store, namespace):
        try:
            jobs.append(JobPosting.model_validate(item.value))
        except Exception as exc:
            logger.debug("Skipping unreadable stored vacancy %s: %s", item.key, exc)
    return jobs


@tool
async def list_known_jobs(
    title_contains: str | None = None,
    location_contains: str | None = None,
    work_mode: str | None = None,
    limit: int = 30,
) -> str:
    """List vacancies already in memory, newest first.

    `research_jobs` reports only what a scan found for the first time, because
    re-listing hundreds of known vacancies on every run would drown the context.
    The consequence is that the best match becomes invisible the moment it stops
    being new, so this is how a vacancy is found again: search memory before
    concluding that something is not there.

    Args:
        title_contains: case-insensitive substring of the job title, e.g. "agentic".
        location_contains: case-insensitive substring of the location.
        work_mode: one of remote, hybrid, onsite.
        limit: how many to return at most.

    Returns:
        One compact card per vacancy, or a note that memory holds nothing matching.
    """
    store = _store()
    if store is None:
        return "Memory is unavailable, so nothing can be listed."

    jobs = await _load_jobs(store, current_user_id(), None)
    if not jobs:
        return "Memory holds no vacancies yet. Run research_jobs first."

    total = len(jobs)
    if title_contains:
        needle = title_contains.lower()
        jobs = [j for j in jobs if needle in j.title.lower()]
    if location_contains:
        needle = location_contains.lower()
        jobs = [j for j in jobs if needle in (j.location or "").lower()]
    if work_mode:
        jobs = [j for j in jobs if j.work_mode.value == work_mode.lower()]

    if not jobs:
        return (
            f"None of the {total} vacancies in memory match that filter. "
            "Try a broader one, or run research_jobs to collect more."
        )

    jobs.sort(key=lambda j: j.posted_at or "", reverse=True)
    shown = jobs[:limit]
    lines = [f"{len(jobs)} of {total} stored vacancies match; showing {len(shown)}:"]
    lines += [
        f"- [{j.canonical_id}] {j.title} - {j.company} | {j.location or 'location not stated'}"
        f" | {j.seniority.value} | {j.work_mode.value}"
        f" | requirements: {len(j.requirements)} | {j.posted_at or 'date not stated'}"
        for j in shown
    ]
    return "\n".join(lines)


def _format_dossier(job: JobPosting) -> str:
    """Render a stored dossier for a subagent, description last and marked untrusted."""
    from ..middleware.injection_guard import wrap_untrusted

    must_have = [r for r in job.requirements if r.kind is RequirementKind.MUST_HAVE]
    nice_to_have = [r for r in job.requirements if r.kind is RequirementKind.NICE_TO_HAVE]
    visa = "not stated" if job.visa_sponsorship is None else str(job.visa_sponsorship)

    lines = [
        f"# {job.title} - {job.company}",
        f"id: {job.canonical_id}",
        f"location: {job.location or 'not stated'} | work mode: {job.work_mode.value}"
        f" | seniority: {job.seniority.value}",
        f"posted: {job.posted_at or 'not stated'} | source: {job.source}",
        f"url: {job.url or 'not stated'}",
        f"salary: {job.salary_raw or 'not stated'}"
        f" | visa sponsorship: {visa}"
        f" | language: {job.language or 'not stated'}",
    ]
    if must_have:
        lines.append("must have: " + ", ".join(r.skill for r in must_have))
    if nice_to_have:
        lines.append("nice to have: " + ", ".join(r.skill for r in nice_to_have))
    if job.tech_stack:
        lines.append("tech stack: " + ", ".join(job.tech_stack))

    if job.description:
        lines.append("\n## Description\n" + wrap_untrusted(job.description))
    else:
        lines.append("\nNo full description was stored: only the card survived the scan.")

    return "\n".join(lines)


@tool
async def read_job_dossier(job_id: str) -> str:
    """Read one stored job dossier by its canonical id.

    Read-only and scoped to the vacancies namespace: nothing else in memory is
    reachable through it. Meant for subagents working on a single vacancy, so
    the full description is digested in an isolated context instead of being
    pulled into the main conversation.

    Args:
        job_id: the canonical vacancy id, e.g. `li:4123456789`.

    Returns:
        The dossier as text, with the raw description marked as untrusted data.
    """
    store = _store()
    if store is None:
        return "Memory is unavailable; the dossier cannot be read."

    item = await store.aget(jobs_ns(current_user_id()), job_id)
    if item is None:
        return (
            f"No vacancy {job_id} in memory. Check the id, or ask the orchestrator "
            "to run research_jobs first."
        )
    try:
        job = JobPosting.model_validate(item.value)
    except Exception as exc:
        logger.warning("Stored vacancy %s is corrupt: %s", job_id, exc)
        return f"The stored record for {job_id} is unreadable."

    return _format_dossier(job)


def _format_profile(profile: CandidateProfile) -> str:
    """Render the stored Candidate Profile for a subagent, evidence quoted verbatim.

    Deliberately not wrapped in the untrusted-data markers, unlike a job dossier.
    This is the owner's own data and the authority the CV is written against; the
    marker's own text tells the model that anything inside it is hostile and must
    not be acted on, which is the opposite of what the iron rule in the cv-writer
    prompt requires. Marking everything untrusted also costs the marker its
    meaning on the content that genuinely is.

    The residual risk is accepted knowingly: `evidence` holds verbatim lines from
    the CV, LinkedIn and personal site, so hostile text there would come through.
    Those are the owner's own documents, and they were already digested once by
    the tool-less structured-output call in `bootstrap_profile`, which is where
    the architectural defence sits.
    """
    lines = [
        "# Candidate Profile",
        f"name: {profile.full_name or '[not stated]'}",
        f"headline: {profile.headline or 'not stated'}",
        f"location: {profile.location or 'not stated'}",
        f"experience: {profile.years_experience:g} years"
        if profile.years_experience is not None
        else "experience: not stated",
        f"right to work: {profile.work_authorization or 'not stated'}",
        f"languages: {', '.join(profile.languages) if profile.languages else 'not stated'}",
    ]
    if profile.open_to_relocation is not None:
        lines.append(f"open to relocation: {profile.open_to_relocation}")
    if profile.salary_expectation:
        lines.append(f"salary expectation: {profile.salary_expectation}")

    if profile.roles:
        lines.append("\n## Roles\n" + "\n".join(f"- {role}" for role in profile.roles))
    if profile.projects:
        lines.append("\n## Projects\n" + "\n".join(f"- {project}" for project in profile.projects))

    if profile.claims:
        claims = []
        for claim in profile.claims:
            years = f", {claim.years:g} years" if claim.years is not None else ""
            last_used = f", last used {claim.last_used}" if claim.last_used else ""
            claims.append(
                f'- {claim.skill} (source: {claim.source}{years}{last_used}): "{claim.evidence}"'
            )
        lines.append("\n## Skills, each with the line that backs it\n" + "\n".join(claims))
    else:
        lines.append("\nNo skills are backed by evidence: the profile is empty in that respect.")

    lines.append(
        "\nAnything absent from the above is absent from the document. Write [placeholder] "
        "and say what is needed rather than filling the hole."
    )
    return "\n".join(lines)


@tool
async def read_candidate_profile() -> str:
    """Read the stored Candidate Profile: the only permitted source of facts about the user.

    Read-only and scoped to the profile namespace: nothing else in memory is
    reachable through it. Every skill comes with the verbatim line that backs it,
    which is what a CV claim has to be built on — a skill without a quote here
    cannot go into the document.

    Returns:
        The profile as text, or an explanation of why there is none to read.
    """
    identity = current_identity()
    if not identity.may_read_owner_profile:
        # Guests are already given an agent without this tool. The check is here
        # because the namespace alone would not stop a guest whose id somehow
        # matched the owner's, and because this is the one tool that returns the
        # CV verbatim: employers, dates, and the evidence lines behind it.
        return "The Candidate Profile belongs to the owner of this agent and is not readable here."

    store = _store()
    if store is None:
        return "Memory is unavailable; the Candidate Profile cannot be read."

    item = await store.aget(profile_ns(current_user_id()), "current")
    if item is None:
        return (
            "The Candidate Profile has not been assembled, so there is nothing to write from. "
            "Ask the orchestrator to run bootstrap_profile first."
        )
    try:
        profile = CandidateProfile.model_validate(item.value)
    except Exception as exc:
        logger.warning("Stored profile is corrupt: %s", exc)
        return "The stored Candidate Profile is unreadable; it has to be rebuilt."

    return _format_profile(profile)


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
    config = get_config()
    store = _store()
    if store is None:
        return "Memory is unavailable; there is nothing to score."

    profile = await _load_profile(store, current_user_id())
    if profile is None:
        return (
            "The Candidate Profile has not been assembled. Run bootstrap_profile — "
            "without a profile the score would be invention rather than assessment."
        )

    jobs = await _load_jobs(store, current_user_id(), job_ids)
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
    store = _store()
    if store is None:
        return "Memory is unavailable."

    profile = await _load_profile(store, current_user_id())
    if profile is None:
        return "The Candidate Profile has not been assembled. Run bootstrap_profile."

    jobs = await _load_jobs(store, current_user_id(), None)
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
    store = _store()
    if store is None:
        return "Memory is unavailable; the preference was not saved."

    data = await load_feedback(store, current_user_id())
    notes = list(data.get("notes", []))
    denied = list(data.get("company_deny", []))

    if note and note not in notes:
        notes.append(note)
    if company_to_avoid and company_to_avoid not in denied:
        denied.append(company_to_avoid)

    await save_feedback(store, current_user_id(), {"notes": notes, "company_deny": denied})
    return f"Noted. Stored preferences: {len(notes)}, companies on the stop-list: {len(denied)}."
