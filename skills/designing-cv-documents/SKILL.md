---
name: designing-cv-documents
description: Use when laying out a CV document, choosing fonts, spacing, colour or page count, rendering a CV to PDF with Typst, or evaluating whether a CV template or visual element is safe to use
---

# Designing CV documents

## Overview

A CV has two readers: a human who skims it and a parser that extracts it. Visual hierarchy
that exists only as size, weight, colour or position carries **no information** into
extracted text. Every design decision has to survive both.

Sources: `docs/research/2026-09-03-cv-ats-linkedin-sources.md` §3.

## Typography numbers

| Parameter | Value |
|---|---|
| Body point size | 10–11 pt. Butterick: "If you're not required to use 12 point, don't." |
| Line spacing | 120–145% of point size |
| Line length | **45–90 characters** including spaces (2–3 lowercase alphabets) |
| Margins | On A4 at 10–11 pt, 20–25 mm all round lands in the measure. Tune to the measure, not to fill the page |
| All-caps | Only below one line, with 5–12% added letterspacing |
| Paragraph separation | First-line indent **or** 4–10 pt space — never both |
| Contrast | 4.5:1 for all body text, 3:1 for rules and accents |

Contrast is where templates fail most often and most invisibly. Grey secondary text at
`#999` on white gives ~2.8:1 and fails; `#666` gives ~5.7:1 and passes. Body text at 10–11 pt
is never "large text", so the 3:1 relaxation does not apply to it. Typst does not check
contrast — verify externally.

Indented bullet lists eat into the measure. Set the initial line length so the *indented*
text still lands in the 45–90 range.

## Hierarchy: emphasise substance, not headings

Butterick's argument, which inverts what most CV templates do:

> the visual emphasis has shifted from the headings—**who cares about résumé headings?**—to
> the substance… Don't make your reader struggle to dig out the names of those schools and
> employers—make sure they're immediately visible.

So: employer names, role titles and dates carry the visual weight. The words "EXPERIENCE" and
"EDUCATION" are navigation furniture and should be quiet.

Two pages is fine and often better than a cramped one. The one-page rule is, in Butterick's
words, a myth whose side effect is unreadable density. But never assume the reader reaches
page two — everything decisive goes on page one.

## Font choice

Serif versus sans-serif is **not a real lever**. The most recent controlled study (2026,
N=132) found no significant effect of font type on comprehension, cognitive load, or reading
time. Don't spend the user's attention on it.

What actually matters:

- **Polish diacritic coverage** — ą ć ę ł ń ó ś ź ż and capitals. Many geometric and display
  sans faces lack a properly drawn ł or ż.
- **Real weights**, not synthesised bold.
- **A licence permitting PDF embedding.** Most OFL and Apache fonts qualify.
- **No icon fonts.** See below — this is a hard technical failure, not a preference.
- No monospace for body text; monospace is fine for code identifiers.

Families that meet these criteria and are free to embed: **Source Serif 4 / Source Sans 3**,
**IBM Plex Serif / Plex Sans**, **EB Garamond**, **Libertinus Serif** (shipped with Typst).
Verify the diacritics yourself before committing — render `ĄĆĘŁŃÓŚŹŻ ąćęłńóśźż` at final size
and look at the ł and ż specifically, since those are the glyphs that most often look wrong.

## Typst specifics

Current: **0.15.1** (July 2026), verified 2026-09-03. Still pre-1.0, so breaking changes
between minor versions are normal — record the version any generated source was authored
against, and re-check the release notes before changing a template. If the installed Typst is
older than 0.14, tagged PDF and the line-break extraction fix are both absent and the version
must be upgraded before it is used for a CV.

This skill assumes the CV is generated from Markdown into Typst. If the candidate insists on
editing an existing DOCX, the typography numbers and the harmful-element list still apply;
only the Typst-specific mechanics below do not.

**Tagged PDF has been the default since 0.14** (October 2025), which also fixed the classic
extraction bug where words fused across line breaks. Do not pass `--no-pdf-tags`.

**Reading order follows markup order, not visual layout.** This changes the column calculus
*within Typst* — it does not make columns safe for a CV, because the parser on the other end
may never read the structure tree. Single column remains the rule; the detail below matters
only when something genuinely must sit side by side.

- `#columns(2)` extracts correctly — flow order matches markup order.
- A **multi-row grid** is the real hazard: it extracts row1-left, row1-right, row2-left,
  which is exactly the scrambling a sidebar layout was trying to avoid.
- `place` and `move` decouple markup from visual position. Put the call where a screen reader
  should announce it.
- Use `table` for tabular data, never `grid` — only `table` produces real structure.

**Use semantic elements.** `= Heading`, real lists, real tables. A `#text(size: 16pt,
weight: "bold")` pretending to be a heading produces no structure tag at all: Typst "cannot
make the assumption that you meant that to be a heading".

**The caveat Typst cannot fix:** many ATS parsers ignore the structure tree entirely and infer
columns from x-coordinates. A well-tagged two-column Typst CV can still scramble for them.
Single column stays the default, and the reason is parser limitations, not Typst.

Reproducible export:

```bash
typst compile cv.typ cv.pdf \
  --pdf-standard ua-1,a-2u \
  --font-path ./fonts \
  --ignore-system-fonts
```

`--ignore-system-fonts` matters: without it the same source renders differently depending on
what happens to be installed. The CLI ships no sans-serif text face, so any sans design must
ship its fonts alongside. Validate with veraPDF and PAC.

## Harmful elements, with reasons

**Skill rating bars, dots, stars, percentage rings.** Three reasons, the third verifiable:
they encode a self-invented score on no shared scale; an 80% ring quietly announces you are
20% short; and Typst marks shapes like `rect` and `circle` as **artifacts** — content
explicitly declared non-semantic. A skill bar isn't merely hard to extract, it is labelled
"ignore me" in the structure tree.

**Icon fonts.** Font Awesome and similar map glyphs into the Unicode Private Use Area, which
PDF/A-2a and A-3a forbid outright. An envelope glyph replacing the word "Email" is
information destroyed. Icons beside a text label are harmless; icons replacing labels are not.

**Tables and text boxes for layout, sidebars, photos in the header, infographics, timelines,
radar charts.** All encode meaning in geometry, all extract as nothing or as fragments, and
all displace text that would have carried the claim verifiably.

**Never underline** except links. **Never combine bold and italic.**

## Safe by default

Single column, generous margins, semantic headings, one restrained accent colour meeting
4.5:1, consistent alignment, a repeating spacing rhythm, plain-text skill lists, and full
URLs written as visible text (link annotations aren't always followed by extractors; the
visible text always is).
