# Sources for the CV, ATS and LinkedIn skills

Research date: 2026-09-03. All URLs were checked on that day.

This document is the source of truth for the files in `skills/`. The skills stay short and
point here for the evidence base. If a rule in a skill contradicts this file, this file
wins. If both are stale, re-verify against the dates in the tables below.

**Citation rule:** every claim in the skills must trace back to a line here.
A claim without a source is labelled as an inference, not as a fact.

---

## 1. ATS: what is confirmed

### 1.1 Auto-rejection is tied to the questionnaire, not to the CV

Greenhouse Auto-Reject can only be configured against job-post questions of the Yes/No,
Single-select and Multi-select types. There is no mechanism for rejecting on the text of a CV.
[support.greenhouse.io/.../360000653472](https://support.greenhouse.io/hc/en-us/articles/360000653472-Auto-reject),
[Application rules overview](https://support.greenhouse.io/hc/en-us/articles/203105595-Application-rules-overview).
Vendor documentation, current as of the verification date.

Consequence: the main surface of real screening-out is the answers to the questions (right
to work, location, minimum experience), not document formatting.

### 1.2 Greenhouse publishes a list of what breaks its parser

[support.greenhouse.io/.../200989175](https://support.greenhouse.io/hc/en-us/articles/200989175-Unsuccessful-resume-parse):
file >2.5 MB; letter-spacing inside words; graphics, photos, word art; a CV as an image;
tables, headers, footers; name and contacts in a header/footer/text block; column
layout; absence of clear sections and inconsistent formatting between them; company
names without a suffix (Inc., Ltd, LLC); abbreviated job titles ("Sr. Account Exec" instead
of "Senior Account Executive"); data that looks like placeholders.

Important: when parsing fails, the CV is **still attached** to the candidate, and the
recruiter fills the fields in by hand. A parsing failure is a data-entry problem, not a
rejection.

### 1.3 Columns: the only public measurements

Textkernel (owner of Sovren), [engineering blog, 2023-10-18](https://www.textkernel.com/improving-extraction-from-column-resumes/):
at least 15% of CVs use a column layout; the old rule-based system made the right
decision in 60% of cases, the ML model raised that to 82%; in a blind evaluation of ~700 CVs
the share rendered well rose **from 62% to 90%**; across >12000 random CVs the fill rate of
contact fields rose by **4–10 percentage points**.

Their own caveat: an imperfect render is "still useful for certain tasks: searching for
keywords is still possible". Columns hurt the extraction of structured fields, not
findability by keyword.

Age: almost 3 years. It describes a fix, so "62%" is a historical baseline for
systems running older parser versions.

### 1.4 Recruiter search is boolean over full text

Ashby, [docs.ashbyhq.com/candidate-search](https://docs.ashbyhq.com/candidate-search):
modes `matches` (all words, any order), `contains` (exact phrase in order),
`equals` (exact phrase with case), `similar` (morphological variants). Operators
`AND/OR/NOT`, quotation marks, `*` for stemming, grouping with parentheses. Their example:
`"senior software engineer" AND (python OR java) AND (remote OR hybrid) AND !(junior OR intern OR contractor)`.

The consequence, the most operationally important one in this whole section: the real
keyword test is **whether the exact phrase the recruiter will type appears as selectable
text in the right order**. Including the negative terms they will exclude on.

### 1.5 Repeating keywords does not raise the score

Greenhouse, [Talent Matching FAQ](https://support.greenhouse.io/hc/en-us/articles/41131886674075-Talent-Matching-FAQ):
"multiple terms can map to the same calibrated skill — so a longer list of matched terms
doesn't always mean a higher match score". The vendor states directly that volume and
repetition of terms do not increase the score. Talent Matching also "does not auto-reject or
auto-advance any candidate", and CVs with formatting problems go to "Needs manual review".

### 1.6 Hidden keywords: prevalence and detection

Zhang et al., "Measuring Real-World Prompt Injection Attacks in LLM-based Resume
Screening", [arXiv:2605.28999](https://arxiv.org/abs/2605.28999), **USENIX Security 2026**,
196 682 real CVs from hireEZ. About **1%** of CVs contain hidden injections; **over
90%** of those are not instructions but hidden keywords and invented experience. Techniques:
text colour matching the background, ~1pt font size, placing text outside the page bounds,
layers. Detectors (font size <4pt, colour distance <15, pixel variance <3.0, ink density
<1.5%, cross-checking the render against the extracted text) are **already running in
hireEZ production**.

This is the most authoritative source in the collection: peer-reviewed, a top-tier security
venue, a large sample, published code.

### 1.7 The "ATS rejects 75% of CVs" myth

The figure is unstable across retellings (70/75/88%), which is itself diagnostic. It traces
back to **Preptel** — a CV-optimisation startup selling a subscription at $24.95/month; it
shut down in 2013 without publishing a methodology, a dataset or a study.
Contemporary article: [CIO.com, 2012-02-29](https://www.cio.com/article/284417/careers-staffing-new-job-search-service-helps-job-seekers-penetrate-applicant-tracking-systems.html).

The report usually used to defend the myth says something different. Fuller, Raman et al.,
"Hidden Workers: Untapped Talent",
[HBS + Accenture, September 2021](https://www.hbs.edu/managing-the-future-of-work/research/Pages/hidden-workers-untapped-talent.aspx):
>90% of employers use software for initial filtering or ranking; 88%
agree that qualified candidates for high-skills roles are screened out because of rigid
criteria **from the job description**, set by the recruiter. That is a claim about
configuration, not about the parser. Separately: almost half of respondents automatically
screen out on an employment gap of more than 6 months — that is, on **parsed dates**.

Freshness caveat: the report's surveys were conducted in January–June 2020, before the era
of LLM screening.

One more figure worth understanding: "99% of the Fortune 500 use an ATS" goes back to
Jobscan — a vendor of CV scanners (in the HBS report it is footnote 79). The current edition
of Jobscan gives 97.4% and describes the method: reverse-engineering careers pages. That
measures **ATS prevalence**, not auto-screening behaviour.

### 1.8 What could not be verified

The documentation of Lever, iCIMS, SmartRecruiters, BambooHR and Oracle Taleo is behind a
login or has been removed. The strong claims above are Greenhouse- and Ashby-shaped. The
platforms with the largest volumes (Workday >40% of the Fortune 500, SuccessFactors 12%,
Taleo, iCIMS) are the worst documented. The Ladders study on "6 seconds per CV" could not be
obtained.

---

## 2. CV content

### 2.1 The XYZ formula — the primary source, verbatim

Laszlo Bock (then SVP People Operations at Google), "My Personal Formula for a Winning
Resume", LinkedIn, **2014-09-29**:

> Every one of your accomplishments should be presented as:
> **Accomplished [X] as measured by [Y] by doing [Z]**

His own worked example, which usually gets lost in retellings: to "improved portfolio
performance by 12%" he adds "($1.2M)", because "adding '($1.2M)' anticipates the reviewer's
question about whether 12% is a big deal or not". **A percentage without an absolute
magnitude and an absolute magnitude without scale are equally defective.** The pair is what
makes a number interpretable.

The formula has entered the institutional canon: CMU CPDC "Resume Essentials" (2024)
reproduces it verbatim. That is adoption of expert opinion, not independent validation.

No published, reasoned critique of the formula could be found. Anyone claiming it has been
"debunked" is making that up. But three tensions are visible inside the primary sources
themselves:

1. XYZ conflicts with the length rules — Bock's examples are far longer than "one or two lines".
2. XYZ conflicts with his own confidentiality rule (see 2.3).
3. **CMU teaches XYZ and does not follow it in its own engineering examples.** In the 2026
   edition of the guide, almost all SWE bullets take the form `Action Verb + Context + Result`
   and carry **no metric**:
   "Developed UI feature enhancements with C++ to extract user inputs…", "Implemented GPU
   kernels for camera correction that were deployed to production robots". A metric appears
   in exactly one of six showcase bullets.

This is the most useful observation in the section: the sources standing closest to
engineering CVs quietly treat measurement as optional and substitute **scale, the fact of
shipping to production, and technical specificity** for it.

### 2.2 Institutional rules

**Harvard FAS**, [careerservices.fas.harvard.edu](https://careerservices.fas.harvard.edu/resources/create-a-strong-resume/),
page dated 2024-07-11, examples updated 2026-07. CV language must be: specific
rather than general; active rather than passive; written to express not impress;
**fact-based (quantify and qualify)**; written for people who / systems that scan quickly.

The phrasing "quantify **and qualify**" is the best four words on the metrics problem in the
whole collection, and they are almost never quoted: Harvard itself permits non-numeric
evidence.

Harvard's top 5 mistakes, in order: spelling and grammar; missing email and phone number;
passive voice instead of action verbs; poor organisation and unreadability; **failure to
demonstrate results**.

The DON'T list: personal pronouns, abbreviations, a narrative style, slang, **a photograph**,
age and gender, a list of referees, starting a line with a date.

Harvard does not regulate length. Harvard's separate PDF handbook, which the internet links
to en masse, **no longer exists** — only the samples remain.

**MIT CAPD**, [checklist, 2022-06-16](https://capd.mit.edu/resources/resume-checklist/):
"Have you kept it to one page? You may use two pages if you have an advanced degree or
extensive experience (10+ years)". And: "Did you give evidence **and** quantify relevant
information (e.g. **size, scale, budget, staff**) for impact?" — here the substitutes for a
metric are named outright.

[MIT, the PAR framework, 2022-07-15](https://capd.mit.edu/resources/resumes-writing-about-your-skills/):
strong verb → relevant task → result → accomplishment. A bullet is 1–2 lines. Descriptions
in paragraphs are called a mistake.

**CMU CPDC**, [Graduate Student Resume Guide, 2026 edition](https://www.cmu.edu/career/documents/sample-resumes-cover-letters/graduate_student_resume_guide_2026.pdf):
the formula `Action Verb + Context (what you did and how) + Result (Metrics, Outcome, and/or Impact)`.
The disjunction matters: a metric is one of three admissible ways to close a bullet.

Length: "one page for every 8-10 years of experience". Bullet: no more than two lines. "The
more relevant/recent an experience, the more detail you should provide".

Skills section: "**Do not include soft skills such as 'teamwork' or 'leadership'**".
Format with levels: `Programming Languages: Advanced - C, C++; Intermediate - Java, Python`.

On the objective/summary: usually unnecessary, **but** it "may be helpful for students with
a diverse or varied background to help to focus the resume … when making a significant career
transition". Avoid generic phrasing such as "To pursue employment in the software
engineering field".

On generative AI: the content must "be verified and expanded upon in the interview
process" and reflect the candidate's own voice. Harvard is stricter: "Generative AI should not
be the primary author—not least because its output will likely be very generic".

**UC Berkeley**, [career.berkeley.edu](https://career.berkeley.edu/prepare-for-success/resumes/):
the chronological format for those "continuing along a prescribed career path in which you
have gained some experience (engineering, for example)"; functional — for a career change.
Moving from SWE into AI engineering is **adjacency, not a career change**, so
chronological.

### 2.3 Honesty and confidentiality

Bock, "The Biggest Mistakes I See on Resumes", 2014-09-17. The test worth hard-coding into
the skill verbatim:

> The *New York Times* test is helpful here: if you wouldn't want to see it on the home
> page of the *NYT* with your name attached (or if your boss wouldn't!), don't put it on
> your resume.

His example of failure: "Consulted to a major software company in Redmond, Washington" →
"Rejected!". **Coy anonymisation is worse than silence.** By his own rough estimate, 5–10% of
CVs disclose confidential information (he himself calls this a "very rough audit").

On lying: "Putting a lie on your resume is never, ever, ever, worth it… Lies follow you
forever".

### 2.4 Engineering specifics

Gayle Laakmann McDowell (ex-Google/Microsoft/Apple, author of "Cracking the Coding
Interview"), CareerCup, [Wayback snapshot from 2014-01-10](http://web.archive.org/web/20140110071208/http://www.careercup.com/resume)
— the live page no longer exists.

Two of her rules are flagged by her as engineer-specific:

> **Projects:** Most candidates should pick their top 3 - 5 projects… **They do not need to
> be completed or launched either. As long as you've done a 'meaty' amount of work on them,
> that's good enough!**

> **Languages and Technologies:** remember that **anything you list here is 'fair game' for
> the interviewer to test.** If you want to list a language but you happen to be a bit
> rusty in it, consider listing it as: "C++ (Proficient), C# (Prior Experience)".

The second is the most important engineering rule in the collection, and it has no analogue
in general advice: the skills section of an engineer's CV is **a commitment to pass a test,
not a keyword list**.

Also from her: "About 50% of candidates leave out an important project… because it wasn't
finished / 'official'. If you've done it, and it's impressive enough to 'make the cut'… it
belongs on your resume!" (the 50% estimate is her own, without a source).

**Two of her rules are out of date and must not make it into a 2026 skill:** she recommends
column templates and Word tables. This is refuted by every later source — MIT,
CMU 2026 ("Avoid tables, text boxes, images. A one column resume is ideal"), Berkeley — and
by Textkernel's measurements. A good reason to date every rule.

### 2.5 The Ladders "7.4 seconds" study — do not use

The archived 2018 PDF was obtained and read. It claims an "average initial screen clocking in
at just 7.4 seconds in 2018". The methodology takes up two lines in the document. **The
sample size is stated nowhere** — neither for recruiters nor for CVs. There is no variance,
no confidence intervals, no distribution. The "initial screen" is not defined. The conditions
are laboratory conditions. The comparison with an earlier measurement is admitted by the
authors themselves to be confounded (that one was taken at the height of the recession). The
publisher is a commercial job board that sold CV-writing services. The preceding 2012 study,
the origin of the "6 seconds", could not be found in the archives at all.

**Conclusion: do not cite the figure as evidence.** If a premise about a cursory scan is
needed, use MIT's honestly hedged phrasing: "Recruiters spend just a few seconds on
average looking at a resume".

The directional findings of Ladders that independently corroborate institutional advice can
be mentioned as weak support: job titles attract attention more strongly than other
elements; short statements read better than paragraphs; keywords are needed in context; the
worst CVs are characterised by "multiple columns and very little white space".

### 2.6 Positioning into a new role

**For "Agentic SDLC Engineer" no settled CV conventions exist in any authoritative source.**
The skill is obliged to admit this rather than pretend a convention exists.

Transferable frames that work:

MIT CAPD, ["Atomize", ~2025-03](https://capd.mit.edu/resources/thinking-about-a-career-pivot-atomize/)
— and it is a software engineer who features in their own example:

> Being a software engineer is a combination of a lot of smaller pieces, like atoms, that
> you can take, recombine, and reconfigure to fit a variety of new directions.

And the instruction on materials: **atomise the job description**, break it down into
keywords and verbs, and "by coopting the language, you connect more closely with the individuals
reviewing your materials".

Google + Center for Veteran Transition and Integration (Columbia),
[blog.google, 2019-10-31](https://blog.google/outreach-initiatives/grow-with-google/resume-tips-for-veterans/):
when the job title does not match the target one, the burden of proving fit is carried by the
vocabulary of the job description. The same operational conclusion, arrived at
independently, from the employer's side.

A tension that will have to be resolved: CMU demands "Avoid jargon that isn't universal to
your field", while AI engineering consists entirely of unsettled jargon (RAG, MCP, evals,
guardrails). The resolution is to expand on first use and keep the abbreviation next to it,
and never to let a term stand in for a claim. "Built RAG pipeline" is a keyword; "Built a
retrieval-augmented generation (RAG) pipeline over 400k internal documents" is a claim.

---

## 3. Design, typography, Poland and the EU

### 3.1 Poland: a klauzula RODO is not required

This is the most practically significant finding of the whole research effort, and it
contradicts the overwhelming majority of Polish-language advice, including publications by
law firms.

**Art. 22¹ §1 of the Labour Code** (version in force from 2019-05-04) — a closed list of the
data an employer demands from a candidate: first name and surname; **date of birth**; the
contact details indicated by that person; education; professional qualifications; employment
history. Items 4–6 only if they are necessary for work of the given type.

**Art. 22¹a** is the decisive provision. §1: consent can only be a basis for processing data
**outside** the list in art. 22¹. §2:

> Brak zgody… lub jej wycofanie, **nie może być podstawą niekorzystnego traktowania** osoby
> ubiegającej się o zatrudnienie… a także **nie może stanowić przyczyny uzasadniającej
> odmowę zatrudnienia**.

§3 extends this to data supplied **on the candidate's own initiative** — that is, exactly the
case of a photograph.

**The regulator's position.** UODO, ["ABC rekrutacji", uodo.gov.pl/pl/701/4471](https://uodo.gov.pl/pl/701/4471)
(2026 in the date markup, so the guidance is current):

> Do przetwarzania wyżej wymienionych danych **nie jest potrzebna zgoda. Dotychczasowa
> praktyka zamieszczenia w liście motywacyjnym CV zgody na przetwarzanie danych w celach
> rekrutacyjnych nie jest właściwa.**

UODO also: the art. 22¹ list is **closed**; the employer has no right to prompt a candidate
as to what additional data they might provide; the duty to inform under art. 13–14 of the
GDPR lies with the **employer**, not with the candidate.

On photos: "Przepisy kodeksu pracy **nie nakładają obowiązku** przekazywania pracodawcy przez
kandydata do pracy swojego zdjęcia".

**The only legitimate use of the clause** is consent to **future** recruitments
(`przyszłe rekrutacje`), which genuinely fall outside art. 22¹ and require consent. No
officially prescribed wording exists; dozens of sites present "the current official
2025/2026 clause" as fact.

**The unreliable-source category.** adwokat-orlicki.pl, gowork.pl, startcv.pl, cvwzory.pl
and similar claim the clause is mandatory and that CVs without it are destroyed. That
directly contradicts UODO and art. 22¹a. The category dominates the results for the query
`klauzula RODO w CV`.

### 3.2 The Poland/US conflict over date of birth

Date of birth is a **statutory field** in the Polish list and a **legal risk** in the US.
EEOC, [Prohibited Employment Policies & Practices](https://www.eeoc.gov/prohibited-employment-policiespractices):
"employers should not ask for a photograph of an applicant", while information about race,
sex, national origin, age and religion "are irrelevant in such determinations" and may be
used as evidence of an intent to discriminate.

The practical resolution: do not include it by default (in Poland this is lawful, since §5
makes disclosure a declaration by the candidate themselves and §2 protects against adverse
consequences) and add it only if a specific Polish process requires it.

Photo conventions across EU countries **could not** be authoritatively confirmed (the
Antidiskriminierungsstelle and ACAS pages are unavailable). The widely repeated picture —
photos accepted in Germany, Austria, Poland and parts of Central Europe, not accepted in the
UK, Ireland, the Netherlands and Scandinavia — remains practitioner knowledge with no primary
source. The safe default (no photo) works in all of those markets, which makes the question
immaterial.

The canonical work on photos in CVs is taken to be Ruffle & Shtudiner, "Are Good-Looking People
More Employable?", *Management Science* 61(8), 2015. **Not even the abstract could be read**
(paywall, bot protection), so its conclusions are not reproduced here.

### 3.3 Europass

[europass.europa.eu](https://europass.europa.eu/en/create-europass-cv) — the official EU
tool, useful for the comparability of formal qualifications, academic mobility, and
applications to the public sector and EU institutions.

In tech hiring it is not expected and its reputation is bad. The most sensible critique is
[Relocate.me](https://relocate.me/blog/working-abroad/the-europass-cv-doesnt-work-for-european-tech-companies-anymore/)
(a European tech job board, **2017-07-20**, i.e. nine years old): there are no fields for GitHub,
Stack Overflow and a portfolio — "almost must-haves for software engineers"; there is no room
for a stack; the personal-skills section eats half an A4 page to no purpose; the logo and the
"Curriculum Vitae" heading waste space. Conclusion: "not obligatory… There's no need to use it".

Caveat: a commercial source, nine years old, and Europass was relaunched in 2020. The
structural critique (the schema still has no GitHub field) holds.

Europass is appropriate only when an employer or a process explicitly requires it. For an
engineer it is never the default.

### 3.4 Typography

Butterick's Practical Typography, [practicaltypography.com](https://practicaltypography.com),
pages marked as updated 2026-07-21. Caveat: self-published by a single author, and he **sells
the fonts he recommends** (he discloses this himself). The structural numbers are generally
accepted; the specific font recommendations are commercially interested.

| Parameter | Value |
|---|---|
| Font size (print) | 10–12 pt, and "if you're not required to use 12 point, don't" |
| Line spacing | 120–145% of the font size |
| Line length | **45–90 characters** including spaces, or 2–3 alphabets |
| Margins (12pt on 8.5×11) | 1.5–2.0″ left and right |
| Letterspacing for caps | +5–12% |
| Paragraph separation | first-line indent **or** 4–10pt of space, not both |

His [page on resumes](https://practicaltypography.com/resumes.html) is the most directly
applicable material:

> The biggest problem I see with résumés is that they're uncomfortably dense with text. I
> take this to be the influence of the **myth that a résumé can only be one page long.**

With his own caveats: never count on the reader reaching the second page — the most important
things go on the first; "My résumé fits on two pages. I'll bet yours can too".

And the main argument about hierarchy, which inverts what most templates do:

> the visual emphasis has shifted from the headings—**who cares about résumé headings?**—to
> the substance… **Don't make your reader struggle to dig out the names of those schools
> and employers—make sure they're immediately visible.**

Rules: no underlining (except links); do not combine bold and italic; caps only for a line
or less; do not use monospaced fonts for body text.

**Serif versus sans is not a lever.** Behaviour & Information Technology, 2026,
[DOI 10.1080/0144929X.2026.2678378](https://www.tandfonline.com/doi/full/10.1080/0144929X.2026.2678378),
N=132, Verdana versus Times New Roman, screen versus paper: "no significant main effects of
font type on any of the three outcome variables" (cognitive load, reading time,
comprehension). There is no interaction with the medium either. The authors honestly note
that they could not establish equivalence to zero (d=0.20, 90% CI −0.09…0.49), so the correct
conclusion is "don't overthink the choice", not "it is proven that the font does not matter".

What does matter when choosing a font for a PDF: coverage of Polish diacritics (ą ć ę ł ń
ó ś ź ż), real weights instead of synthetic bold, a licence that permits embedding, and the
absence of icon fonts.

### 3.5 Typst

The current version is **0.15.1, released 2026-07-17** (verified via the GitHub releases API).
The project is **pre-1.0**; breaking changes between minor versions are normal — generated
source must pin the version it was written against.

**Tagged PDF by default since 0.14.0 (2025-10-24)**, with the export rewritten onto krilla.
[Release notes](https://github.com/typst/typst/releases/tag/v0.14.0): "Typst PDFs are now
tagged by default", with PDF/UA-1 support. The same release fixed text extraction: "Spaces
between words at which a natural line break occurred are now correctly retained for text
extraction" — historically the main way PDF CVs broke during parsing.

**Reading order follows markup order, not the visual layout.**
[Accessibility guide](https://typst.app/docs/guides/accessibility/): "Typst markup already
implies a single reading order… a grid's contents will just be read out flatly, in the order
that you have added the cells in the source code". Three consequences follow:

- `#columns(2)` is safe: markup order coincides with the visual order.
- A grid with **several rows** is where it breaks: row1-left, row1-right, row2-left…
  That is precisely the interleaving people were trying to avoid.
- `place` and `move` are the real danger; they decouple markup from visual position.

**An important caveat Typst cannot fix:** many ATS parsers do not read the tag tree at all
but extract text geometrically and infer columns from coordinates. Against such a parser, a
carefully tagged two-column Typst document will still get interleaved. One
column remains the less risky choice, and the reason is parser limitations, not Typst.

**The icon-font trap.** PDF/A-2a and A-3a forbid code points from the Unicode Private Use
Area, and icon fonts such as Font Awesome map their glyphs into exactly that range. So an icon
font hard-breaks export to PDF/A-2a/2u/3a/3u, and in ordinary PDF it extracts as garbage. That
moves "don't rely on icons" from a matter of taste to a checkable technical rule.

Typst marks shapes such as `rect` and `circle` as **artifacts** — that is, content explicitly
declared non-semantic. A skill bar drawn with a rectangle does not merely extract badly:
it is flagged "ignore me" in the tag tree.

Fonts bundled with the CLI: Libertinus Serif, New Computer Modern, NCM Math, DejaVu Sans Mono —
**there is no sans-serif for body text among them**. For reproducibility you need `--font-path`
together with `--ignore-system-fonts`, otherwise the same source renders differently on
different machines.

Recommended invocation:

```bash
typst compile cv.typ cv.pdf \
  --pdf-standard ua-1,a-2u \
  --font-path ./fonts \
  --ignore-system-fonts
```

Checking: [veraPDF](https://verapdf.org/) for PDF/A and PDF/UA conformance,
[PAC](https://pac.pdf-accessibility.org/en) for PDF/UA and WCAG. Typst **does not check
contrast itself** and does not reach WCAG AAA. Open issue on file size with tagging:
[typst#7142](https://github.com/typst/typst/issues/7142).

### 3.6 Contrast

WCAG 2.1 SC 1.4.3, [w3.org](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html):
AA requires **4.5:1** for normal text, **3:1** for large text (≥18pt, or bold ≥14pt) and
for graphical objects. The values are not rounded: 4.499:1 fails.

For a CV this means practically all text must clear 4.5:1, since a body size of
10–11pt is by definition below the "large" threshold. Hence a concrete defect in popular
templates: grey secondary text at `#999` on white gives about 2.8:1 and fails, whereas
`#666` gives about 5.7:1 and passes.

What carries over from WCAG to PDF is whatever is a property of the document itself:
contrast, colour as the sole carrier of meaning, text alternatives, reading order, structure,
document language. What does not carry over is whatever requires control at reading time —
for example SC 1.4.12 Text Spacing, since, as Typst themselves admit, "we are not aware of a
PDF viewer with this feature".

---

## 4. LinkedIn

Separating the sources, which is critical for this domain: `linkedin.com/help/*`,
`linkedin.com/blog/engineering/*` and `business.linkedin.com` are **official**.
`linkedin.com/pulse/*` and `linkedin.com/top-content/*` are **user-generated content**
that merely lives on the LinkedIn domain. One such page turned out to contain, all at once,
"21x views", "LinkedIn lets you add 50 skills" (wrong, 100) and "LinkedIn
ranks by endorsements" (undocumented).

### 4.1 Search architecture

[LinkedIn Engineering, "The AI Behind LinkedIn Recruiter search and recommendation systems"](https://www.linkedin.com/blog/engineering/recommendations/ai-behind-linkedin-recruiter-search-and-recommendation-systems)
— no date on the page, ~2019 by internal indications. Plus Geyik et al., SIGIR 2018,
[arXiv:1809.06481](https://arxiv.org/abs/1809.06481).

Two stages: candidate selection, then multi-pass ranking. The query is hybrid: the structured
part — "canonical title(s), canonical skill(s), and company name" — plus
free text.

**The optimisation target is not relevance but InMail Accept**: the candidate received a
message and responded positively. The ranking explicitly rewards predicted responsiveness.

The key quote on where the embeddings work:

> because the retrieval process is doing **exact match based on title ids**, the
> embedding-based similarity won't differentiate the retrieved results by much… We
> implemented a query expansion strategy that adds results with semantically similar titles
> … **when the number of returned results from the original query is too small.**

So the semantic rescue is conditional: it only fires when there are few results. For a
broad search such as "Machine Learning Engineer, Poland" the expansion most likely will not
fire, and a non-standard job title simply will not enter the candidate set.

The age of the source is the main risk: the specific models (GBDT, LINE, GLMix) should be
treated as historical, while the **principles** — standardisation, retrieval by entity ID,
optimisation for mutual interest — are corroborated by today's product documentation.

### 4.2 What is officially documented

[Boolean in Recruiter, help/recruiter/answer/a415295](https://www.linkedin.com/help/recruiter/answer/a415295)
— the single most valuable page. Keywords are highlighted "on the candidate's
profile card, in the **Summary** section, in the **Experience** section (in the header,
description, or location), and in the **Skills** section". That is an official enumeration of
the fields. Honesty caveat: this is stated about highlighting, not about indexing; LinkedIn
publishes field weights nowhere, and anyone naming specific weights is making them up.

Boolean facets: job titles, location, companies, Skills and Assessments, schools,
industries, languages. **Certifications are not on that list.**

[Boolean syntax, a524335](https://www.linkedin.com/help/recruiter/answer/a524335):
operators in upper case; **wildcards `*` are not supported**; stop words are
silently dropped, with the official list being: *and, or, the, of, at, by, to, for, with, in,
they, have, from, not, but, after*. LinkedIn's own example: a search for "after sales" will
return profiles that merely contain "sales".

[Recommended Matches, a413241](https://www.linkedin.com/help/recruiter/answer/a413241):
"You might get **fewer or no Recommended Matches for non-standardized job titles**".

[Spotlights, a414283](https://www.linkedin.com/help/recruiter/answer/a414283). "Active
talent" is defined as "members who recently **updated their LinkedIn profiles**, chose to
share a resume with recruiters, have been in their current roles longer than the average
tenure". **Posting is not among the inputs.** "Interested in your company"
fires on following a company page and reacting to its posts — that is, on
engagement with the **employer's** content, not your own.

[Open to Work, a507508](https://www.linkedin.com/help/linkedin/answer/a507508): the
"Recruiters only" mode gives the full effect in search and spotlights without the public frame
(confirmed in [a419131](https://www.linkedin.com/help/recruiter/answer/a419131)).
Hiding it from the current employer relies on the "I am currently working here" flag.
Auto-expiry: after two consecutive unanswered InMails a confirmation email arrives, and
without a reply the status is **removed automatically**.

[Profile level meter, answer/391](https://www.linkedin.com/help/linkedin/answer/391),
updated ~2026-03: profile completeness "helps improve the discoverability of your profile in
search results". Seven sections for All-star: photo, **location**, **industry**, education,
position, skills, About.

[Skills, a549047](https://www.linkedin.com/help/linkedin/answer/a549047) (~2026-03) and
a568137: the limit is **100**, not 50. And separately
[a565106](https://www.linkedin.com/help/linkedin/answer/a565106): "The 100-skill limit
applies only to the Skills section. Skills associated with roles in your Experience section
aren't included in this limit". Skills cannot be translated into another language — only
deleted and re-added, **with irrecoverable loss of endorsements**.

[Skill Assessments, a507663](https://www.linkedin.com/help/linkedin/answer/a507663):
"LinkedIn Skill Assessments are **no longer available**". A significant share of published
advice still recommends taking them.

[Search Appearances, a553050](https://www.linkedin.com/help/linkedin/answer/a553050)
(~2026-04): "Job titles you were found for", the top job titles of searchers, impressions by
section. This is **the only official instrument for measuring** the result of edits.

### 4.3 Folklore

**"21x views for a photo"** contradicts LinkedIn's own help. Help page
[a554351](https://www.linkedin.com/help/linkedin/answer/a554351) (~2026-03) says "up to
**2X** more profile views", while a LinkedIn marketing post says "21 times". An
order-of-magnitude discrepancy, with no methodology in either place. Even taken on trust it is
an observational correlation. The "36x messages" figure could not be traced to any LinkedIn source.

**"Post weekly so recruiters find you"** is not supported by a single
official source. The documented mechanisms are "update your profile" (Active talent) and
"follow target companies" (Interested in your company). Posting may have
second-order value for networking, but it is not a lever on search visibility.

**"A custom URL improves SEO"** — LinkedIn frames the purpose as identification and
sharing, and explicitly disclaims control over indexing by external search engines. It has no
effect whatsoever on search inside Recruiter. It can be changed 5 times in 6 months, then it locks.

**"Endorsements affect ranking"** is partly official: LinkedIn says they
"reinforce their weighting". But neither the mechanism, nor a threshold, nor a magnitude is
published, and endorsements do not feature in the descriptions of ranking features. Present
as "officially stated, magnitude unknown, probably small".

### 4.4 Character limits

**No official source could be found for any of the profile character limits.** The help pages
for the headline, About, profile editing and skills were checked. The only officially
documented length constraint is the custom URL: 3–100 characters.

| Field | Value | Status |
|---|---|---|
| Skills in the Skills section | **100** | Official |
| Skills on roles in Experience | **outside the 100 limit** | Official |
| Custom URL | **3–100** | Official |
| Headline | 220 | Third parties, consensus |
| About | 2600 | Third parties, consensus |
| Role description | 2000 | Third parties, weaker |
| About truncation ("see more") | ~250–350 | Third parties **contradict each other** |

A 220-character headline is a relatively recent state of affairs (previously 120 on desktop
and 220 on mobile). The reliable tactic: the agent does not rely on a cached number but asks
for a check in the live editor, which hard-blocks input beyond the limit.

---

## 5. Re-verification schedule

| What | Frequency | Why |
|---|---|---|
| LinkedIn limits and mechanics | 6 months | The product changes and the limits are not officially documented |
| Typst version and capabilities | Before every template change | Pre-1.0, breaking changes between minors |
| The UODO position and art. 22¹ | 12 months | A legal provision; the cost of an error is high |
| ATS vendor documentation | 12 months | Greenhouse's Talent Matching appeared between two of their own publications |
| CV content rules | 24 months | Institutional guides change slowly |
