---
name: optimizing-linkedin-profile
description: Use when recommending changes to a LinkedIn profile, when a user asks why recruiters aren't finding them, or when evaluating advice about headlines, skills, endorsements, Open to Work, or posting frequency
---

# Optimising a LinkedIn profile

## Overview

LinkedIn Recruiter retrieval runs on **standardized entity IDs — canonical job titles,
canonical skills, standardized location — not free text.** Whether you are retrieved into the
candidate set at all is governed by standardization. Your prose only matters afterwards, at
ranking and keyword-filter time.

This inverts the usual advice. Headline wording is second-order. Canonical job titles are
first-order.

Sources: `docs/research/2026-09-03-cv-ats-linkedin-sources.md` §4.

## Source discipline

`linkedin.com/help/*` and `linkedin.com/blog/engineering/*` are official.
`linkedin.com/pulse/*` and `linkedin.com/top-content/*` are user-generated content that
merely lives on LinkedIn's domain. One such page carried three false claims at once: "21x
profile views", "50 skills" (the cap is 100), and "LinkedIn ranks by endorsements".

## Tier 1 — determines whether you are retrieved

1. **Every Experience job title must be one a recruiter would pick from a dropdown.**
   Retrieval is "exact match based on title ids", and LinkedIn documents that non-standardized
   titles produce "fewer or no Recommended Matches". Semantic query expansion only fires when
   result counts are too low, which won't happen for a broad search.
   Split the job across three fields: **title** = canonical, **headline** = the interesting
   version, **description** = the long tail.
   **The title field states the role actually held, never the target role.** The honesty gate
   from `writing-cv-content` applies here in full: a profile is a claim about employment, and
   putting "AI Engineer" in the title of a backend job is fabrication, not optimisation.
   When the target role has no canonical title at all — "Agentic SDLC Engineer" almost
   certainly has none — chasing it in the title field is doubly pointless. Pick the nearest
   canonical title that is *true* (`Software Engineer`, `Senior Backend Engineer`,
   `Machine Learning Engineer` if genuinely earned) and carry the target vocabulary in the
   headline, the description, and skills, where it is searchable and honest.
2. **Pick skills from the typeahead, never invent strings.** Only canonical skill IDs
   participate in the facet and the co-occurrence graph.
3. **Use the real skills budget: 100 in the Skills section, plus unlimited skills tagged to
   Experience roles**, which are exempt from the cap. Most people use under 20.
4. **Set Location to the city**, "Warsaw, Mazowieckie, Poland", not the country.
5. **Set Industry.** Most people leave it at whatever LinkedIn guessed.
6. **Open to Work set to "Recruiters only".** Full search and spotlight benefit, no public
   `#OpenToWork` frame, and LinkedIn actively suppresses it from Recruiter users at the
   current employer — keyed on the "I am currently working here" checkbox, so verify it.
7. **Fill in job types and preferred locations**, not just the toggle. The documented search
   benefit is conditional on specifying them.
8. **Set workplace type to include Remote and Hybrid.** This is the specific mechanism that
   puts a Warsaw-based engineer into a Berlin or Amsterdam recruiter's remote-candidate pool.
9. **Answer recruiter InMails, even to decline.** Two consecutive non-responses triggers a
   confirmation email, and ignoring it **silently removes Open to Work**.

## Tier 2 — ranking and conversion

Keyword matches are officially documented to land in: the profile card, the About/Summary
section, the Experience section (header, description, and location), and Skills.

10. **Write Experience descriptions.** Largest searchable free-text field on the profile, and
    the most commonly left empty.
11. **Spell out every abbreviation alongside its expansion.** There is **no wildcard support**
    in LinkedIn search, so `RAG` and `Retrieval-Augmented Generation` are separate strings and
    "engineering" won't match a search for "engineer".
12. **Don't build a phrase on a stop word.** LinkedIn silently drops *and, or, the, of, at,
    by, to, for, with, in, they, have, from, not, but, after*. "Agents for production" indexes
    as "agents production".
13. **Write the headline for a human scanning a result list.** Ranking optimises for **InMail
    Accept** — a human deciding to message you. A pipe-delimited keyword dump lowers exactly
    the thing being optimised. Put the keywords in Experience and Skills, where they're
    searched and cost nothing.
    Shape: current role, strongest evidence, direction of travel. "Backend engineer, 8 years
    in Python and Go — now building LLM agents that review code" beats
    "Backend | Python | Go | K8s | AWS | LLM | RAG | LangGraph | Open to work".
14. **Keep About to one or two front-loaded paragraphs.** This is LinkedIn's own advice, and
    it contradicts the common push to fill all 2,600 characters.
15. **Reorder Skills deliberately.** Skills and Education are the only reorderable sections.

## Cheap documented actions, instead of a content habit

16. **Update the profile periodically.** "Recently updated their profile" is a named input to
    the **Active talent** spotlight — the mechanism people mistakenly attribute to posting.
17. **Follow target companies and engage with their posts.** This is the documented route
    into the **"Interested in your company"** spotlight, which their recruiters filter on.
18. **Connect with people at target companies** — the "Have company connections" spotlight.
19. **Complete profile verification** — Verifications is a real recruiter spotlight.
20. **Hit All-star:** photo, location, industry, education, position, skills, About. LinkedIn
    states directly that completeness improves search discoverability.

## Corrections to common advice

| Claim | Status |
|---|---|
| "Post weekly to be found by recruiters" | **No official support.** Posting is absent from every documented spotlight and ranking description. Frame it as networking, not search visibility. |
| "Photos get 21x more views" | LinkedIn's own help page says "up to **2X**". The 21x figure is marketing with no methodology. Have a photo anyway — for credibility, not ranking. |
| "Add up to 50 skills" | Stale. The cap is **100**. |
| "Take Skill Assessments" | **Officially discontinued.** The Recruiter filter is still named "Skills and Assessments", which keeps this zombie alive. |
| "A custom URL improves SEO" | Only affects external search engines, which LinkedIn explicitly disclaims control over. Zero effect on Recruiter search. Do it once for tidiness — five changes in six months triggers a lockout. |
| "Endorsements drive ranking" | Officially "reinforce their weighting", but no mechanism, threshold, or magnitude is published. A few genuine ones on top skills; no swapping schemes. |
| "Certifications are searchable" | Not a Boolean facet and not in the highlighted-fields list. Their value is realised through the associated **skill**. |

## Measurement

Use **Profile → Analytics → Search Appearances** as the feedback loop. "Job titles you were
found for" and impressions-per-section are the only officially provided signal of whether a
change worked. Baseline before changing anything.

## Character limits — verify, don't trust

**LinkedIn documents no character limit for any profile field.** Officially confirmed:
100 skills, Experience-role skills exempt, custom URL 3–100 characters. Everything else
(headline 220, About 2,600, role description 2,000) is third-party consensus only, and the
About "see more" fold is disputed even between good third-party sources.

Have the user check the live editor, which hard-blocks input at the cap. That beats any
cached number.

## Profile is not a CV

A CV is targeted per application; a profile is retrieved by many different queries, so it must
cover the **union** of plausible search terms rather than the intersection relevant to one
role. A CV is read by someone who already chose to read it; a profile is scanned in a result
list where ranking optimises for whether a human messages you.

First person and a narrative tone are practitioner convention supported by these mechanics —
not documented LinkedIn policy. Say so if asked.

## Polish-profile gotchas

If edits appear not to apply, check whether a secondary Polish-language profile is being
edited instead. And never delete a skill just to change its language — that permanently
destroys its endorsements.
