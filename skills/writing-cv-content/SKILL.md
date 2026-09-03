---
name: writing-cv-content
description: Use when drafting, rewriting, or reviewing the text of a CV or resume — bullets, summary, skills section — including when the candidate lacks clean metrics, is targeting a role they haven't formally held, or asks how to describe confidential work
---

# Writing CV content

## Overview

Every line must be evidence the candidate can defend in an interview. The agent drafts; the
candidate is the author and the one who will be questioned.

Sources for every rule: `docs/research/2026-09-03-cv-ats-linkedin-sources.md` §2.

## The honesty gate — non-negotiable

**If a skill, project, or number is not in the Candidate Profile, it does not go in the CV.**

The Candidate Profile is the agent's stored, structured record of the candidate's real
experience — roles, dates, systems, technologies, projects, and any metrics they have
actually confirmed. It is assembled once from their existing CV, public LinkedIn, and
personal site, and it is the only admissible source of fact. **If no profile has been
assembled yet, say so and gather the facts before drafting** — treating a few sentences in
chat as a profile is how invented detail gets in.

Rewriting existing experience into the vocabulary of the target role is legitimate.
Inventing experience is not. The test is whether the candidate can, unprompted, explain how
a number was derived, who measured it, and over what window. If they cannot, replace the
number with scope or adoption evidence — do not soften it into a vaguer number.

**Approximate but genuinely measured numbers are allowed.** "Cut p99 latency by roughly a
third" is admissible if the candidate really measured it and can say how; the ban is on
numbers that were never measured. And a number the candidate can *derive now* from records
that already exist — counting merged PRs from bot history, repositories from a config,
months from a first-commit date — is legitimate and usually the fastest way to strengthen a
draft. Counting what happened is not the same as inventing what happened.

**When a required fact is missing, do not fill it in.** Draft the line with an explicit
`[placeholder]` naming exactly what you need, and tell the candidate to replace it. Never
guess a stack, a scale, or a platform to make a bullet read better — that is the guess they
will have to defend in an interview.

Laszlo Bock's rule on confidential material, applied to every bullet:

> The *New York Times* test is helpful here: if you wouldn't want to see it on the home page
> of the *NYT* with your name attached (or if your boss wouldn't!), don't put it on your
> resume.

Coy anonymisation is worse than omission. "Consulted to a major software company in Redmond,
Washington" is a rejection, not a clever dodge. When a metric is confidential, move to a
different metric — don't obfuscate the client.

## Bullet construction

Default form, from CMU's current guidance:

```
Action verb + Context (what you did and how) + Result (metric, outcome, and/or impact)
```

Use Bock's XYZ formula — *Accomplished [X] as measured by [Y] by doing [Z]* — as the
**aspiration** for bullets where a real, disclosable, defensible number exists. Do not force
it everywhere. CMU teaches XYZ and then writes engineering bullets without metrics; only one
of six showcase software bullets in their 2026 guide carries a number.

**When you use a number, make it interpretable.** A percentage needs its absolute; an
absolute needs its scale. "Improved performance by 12%" is weak; "improved portfolio
performance by 12% ($1.2M)" answers the reader's real question.

One to two lines per bullet, one being better. No paragraphs. No first-person pronouns. Past
tense for previous roles, present for current.

## Metric substitution ladder

When no clean number exists, descend this ladder rather than inventing one:

1. Disclosable metric with a baseline or peer comparison
2. Scale — dataset size, request volume, team size, number of systems, users
3. Deployment status — shipped to production, adopted by another team
4. Adoption by others — dependents, installs, internal standard
5. Selection ratio or recognition — "one of 230 selected nationwide"
6. Precise qualitative outcome

Harvard's instruction is "fact-based (quantify **and qualify**)" — the second verb is the
permission almost nobody quotes. MIT names the substitutes explicitly: *size, scale, budget,
staff*.

For an adjective you can't drop, attach evidence: "X as demonstrated by Y". The adjective
isn't the problem; the unevidenced adjective is.

## Skills section

**Anything listed is fair game for the interviewer to test.** This is the rule with no
analogue in general resume advice, and it comes from an engineer who sat on Google's hiring
committee. Label proficiency where it is uneven: `Advanced — Python, Go; Prior experience — Rust`.

Never list bare soft skills. CMU: "Do not include soft skills such as 'teamwork' or
'leadership' in this section."

Never list a framework the candidate has read about but not built with. It invites a question
they will fail.

Three levels are usually enough, and the middle one matters most for a pivot, where the
target-role technologies are real but younger than the core stack:
`Advanced — Python, Go, Kubernetes; Working experience — LangGraph, MCP; Prior experience — Rust`.

## Positioning for a role not yet held

**No authoritative source defines resume conventions for "Agentic SDLC Engineer" or AI
engineering roles.** Say so rather than implying a convention exists.

What does apply:

- **Reverse-chronological, not functional.** Software engineering to AI engineering is an
  adjacency, not a career change. A functional layout reads as concealment.
- **Include a positioning summary.** Sources conflict — McDowell says never, CMU says usually
  not — but CMU's explicit carve-out is "a diverse or varied background… when making a
  significant career transition", which is precisely this case. Under 50 words, opens with
  the role noun, evidence-dense. "Aspiring AI engineer, passionate about LLMs" is the exact
  failure mode CMU names.
  **Open with the role the candidate can currently evidence, then bridge to the target** —
  "Backend engineer with 8 years in Python and Go, building LLM agent systems for the past
  year: …". Claiming the target role as a current identity fails the honesty gate.
  The line between a positioning summary and a banned objective statement is direction of
  claim: a summary states what the candidate *has done*; an objective states what they
  *want*. Drop any clause beginning "seeking", "looking for", or "aiming to".
- **Atomize the job posting.** Break it into its verbs and terms, and adopt that vocabulary
  where it honestly describes the candidate's work. When the title doesn't match, the
  posting's language carries the burden of proof of fit.
- **Unfinished and unlaunched work counts.** "They do not need to be completed or launched
  either. As long as you've done a 'meaty' amount of work on them, that's good enough." For a
  pivot built on side projects and internal tooling, this is the most consequential
  permission available.
- **Spell out the jargon.** "Built RAG pipeline" is a keyword. "Built a retrieval-augmented
  generation (RAG) pipeline over 400k internal documents" is a claim.

## Remove on sight

Objective statements ("To pursue employment in…"), references or "references available on
request", bare soft-skill adjectives, first-person pronouns, photos and age and marital
status, narrative paragraphs, home address, decodable client anonymisation, exaggeration of
any kind, irrelevant old material, laundry-list hobbies, "Curriculum Vitae" as a title, and
responsibility-oriented bullets ("Responsible for…") in place of accomplishments.

Passive voice is Harvard's **third** most common resume mistake. Not demonstrating results is
their fifth.

## Length

One page per 8–10 years of experience for US-style resumes. Two A4 pages is the normal
working maximum in Europe, and is standard at mid-to-senior level.

**Pick the convention by the employer's market, not the candidate's.** A US company hiring
remotely gets the US convention even if the candidate lives in Warsaw. When the posting is
ambiguous, default to the European two-page ceiling for EU-based employers and say which
convention you applied, so the candidate can overrule it.

Either way, everything decisive goes on page one — never assume the reader reaches page two.

**Never justify a length rule with a scanning-time statistic.** The "recruiters spend 6
seconds" figure is unverifiable and the 7.4-second study discloses no sample size and no
statistics. If a scanning premise is needed, hedge honestly the way MIT does: "recruiters
spend just a few seconds on average."
