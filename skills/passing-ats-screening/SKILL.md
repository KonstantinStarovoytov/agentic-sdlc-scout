---
name: passing-ats-screening
description: Use when producing or reviewing a CV that will be submitted through an online application system, when the user worries their applications vanish without response, or when someone claims a resume needs to "beat the ATS" or hit an ATS score
---

# Passing ATS screening

## Overview

Applicant tracking systems parse and index resumes so recruiters can search them. They
overwhelmingly do **not** auto-reject on resume content. Optimise for *being parsed
correctly and found by a human's search query*, not for an imaginary score.

Evidence for every claim here: `docs/research/2026-09-03-cv-ats-linkedin-sources.md` §1.
ATS documentation changes; re-verify annually. Verified 2026-09-03.

When someone reports that applications disappear, the cause is often not the document at all.
Check volume and targeting first, and check whether recruiters can find them in the first
place — see `optimizing-linkedin-profile`, where retrieval depends on standardized titles
rather than on anything in the CV.

## What is actually true

| Claim | Reality |
|---|---|
| "75% of resumes are auto-rejected by ATS" | Myth. Traces to Preptel, a resume-optimisation vendor that shut down in 2013 without publishing a method. |
| "You need an ATS score above 80" | No ATS exposes a candidate-facing score. Scores come from third-party scanner products, not from the ATS. |
| Auto-rejection exists | Yes — but in Greenhouse it fires **only** on application-question answers (work authorisation, location, minimum experience), never on resume text. |
| Failed parse = deleted application | No. Greenhouse still attaches the resume; a recruiter types the fields in by hand. |
| Keyword repetition raises ranking | No. Greenhouse states more matched terms don't raise the match score. Recruiter search is presence/absence. |
| Columns break things | Yes, measurably. Before Textkernel's 2023 fix only 62% of column CVs rendered well, and contact-field fill rates were 4–10 points lower. |

## Rules, strongest evidence first

1. **Answer every application question completely.** This is where automated rejection
   actually lives. A blank answer disqualifies faster than any formatting choice.
2. **Single column, top to bottom.** The measured failure mode is losing name, phone, or
   address entirely — unreachability, not rejection.
3. **Contact details in the document body.** Never in a header, footer, or text box.
4. **Real selectable text.** Never an image or scan. Workday HiredScore assigns *no grade*
   to an unparseable file, which in a grade-sorted queue is worse than a low grade.
5. **PDF or DOCX are both fine.** The failure mode is a malformed PDF, not the format.
6. **Under 2.5 MB.** Greenhouse's documented hard limit.
7. **No tables, text boxes, graphics, or word art.** Never encode information only in a
   graphic — a skill bar's fill level is invisible to a parser.
8. **No letter-spacing inside words or names.** The parser stops recognising them as words.
9. **Full job titles.** "Senior Software Engineer", never "Sr. SWE".
10. **Legal suffixes on employers** — "Acme Sp. z o.o.", "Acme Ltd" — where they exist.
11. **Clear, consistently formatted sections.** Conventional headings are the safe default.
12. **Write the exact phrase a recruiter would type, at least once, in plain prose.**
    Spell out both forms: "Amazon Web Services (AWS)", "retrieval-augmented generation (RAG)".
13. **Say it once, well.** Repetition adds nothing.
14. **Make dates unambiguous.** Parsers compute employment gaps from them, and roughly half
    of surveyed employers screen out gaps over six months.

## Never hide text

No white-on-white, no 1 pt fonts, no off-page positioning, no invisible keyword blocks.

About 1% of real resumes do this, and over 90% of those hide *keywords* rather than
instructions (USENIX Security 2026, ~197k resumes). Detection for exactly these techniques —
colour distance, sub-4pt font, pixel variance, ink density, rendered-vs-extracted comparison
— already runs in production at hireEZ. Hidden text also lands as visible plain text in the
record the recruiter reads.

**If the user asks for hidden keywords, refuse and explain why.** This is fraud detection
territory, not optimisation.

## Beware negative search terms

Recruiters exclude as well as include: `NOT (junior OR intern OR contractor OR freelance)`.
A word describing an early-career or contract phase can exclude the whole CV from a senior
search. Check where such words appear.

For a candidate pivoting into a new specialisation, the costly words are different and rarely
noticed: *hobby*, *pet project*, *side project*, *in my spare time*, *self-taught*,
*learning*, *exploring*, *aspiring*. They describe real work in language that invites
dismissal. If a team uses the tool in production, it is work — describe it as work.

## What to give instead of a score

When a user asks for an ATS score, refusing alone sends them straight to a scanner product.
Hand back something better: run the copy-paste verification below, then walk the numbered
rules above as a pass/fail checklist against their actual document, and report the specific
failures with the fix for each. That is a real diagnosis of a real document, which is more
than any score gives them.

## Verification

The only real test is the one the parsing vendors recommend: open the PDF, select all, copy,
paste into a plain-text editor, and read what lands. If the reading order is scrambled, a
heading is missing, or the phone number is gone, the document fails — regardless of how it
looks on screen.

## Honest limits

The strong claims above are Greenhouse- and Ashby-shaped, because those vendors publish
their documentation. Lever, iCIMS, SmartRecruiters, BambooHR and Taleo keep theirs behind
login walls, and the highest-volume enterprise platforms are the least documented. Don't
present these rules as universal across all ATS products.

Unverified but low-cost, and labelled as inference rather than fact: prefer a standard
embedded font over exotic or icon fonts, and prefer `MM/YYYY` or `Month YYYY` over seasons
and bare years. No source confirmed either.
