# Agentic SDLC Scout — design document

**Date:** 2026-09-03
**Status:** approved, ready for an implementation plan
**Phase:** 1 of 3 (agent core; deployment and chat interfaces are separate phases)

### Implementation status

Reconciled against the implemented code on 2026-09-03. Everything described here is what the code
actually does, unless the section carries a bold **Not implemented in phase 1.** line directly under
its heading. That marker means the reasoning still stands and the section is kept as the plan, but
nothing in it exists yet — do not go looking for it in `src/`.

## 1. The problem

An agent that researches open vacancies on the **Agentic SDLC Engineer** track and adjacent roles,
extracts the requirements from them, honestly assesses how well the user's profile matches, and on
request generates a CV tailored to a specific vacancy or text blocks for updating the LinkedIn profile.

A separate and no less important function is the **aggregated gap analysis** across the whole corpus
of vacancies: not "what is missing for vacancy #5", but "which skill is demanded most often, and you
do not have it".

### Not in scope for phase 1

- Container deployment and an OpenAI-compatible shim for OpenWebUI (phase 2)
- A chat widget on the user's personal page (phase 3)
- Background periodic scanning and notifications (architecturally provided for, switched on later)
- Sending messages and connection requests on LinkedIn (deliberately excluded, see §5)

## 2. Key constraints and decisions taken

| Question | Decision | Reason |
|---|---|---|
| LinkedIn access | `stickerdaniel/linkedin-mcp-server` over MCP | The only route to structured LinkedIn data; gives `search_jobs`, `get_job_details`, `get_person_profile`, `get_company_profile` |
| LinkedIn account | A separate burner account | Under the hood it automates a real browser (Patchright Chromium); the risk of a ban must not touch the main profile |
| User profile | A combination: CV file + public LinkedIn + personal page, with gaps filled in by questions in chat | No single source is complete or current on its own |
| Operating mode | On-demand from chat | Background scanning gets added later without a rewrite: the storage schema is already ready for it |
| Storage | Postgres on the Neon free tier + pgvector | The same code locally and in production, semantic search over memory, no migration before deployment |
| Output | Markdown as the source of truth + PDF rendering on request + text blocks for LinkedIn | ATS-friendly, versioned in git |
| LinkedIn profile updates | Copy-paste text only | The MCP has no profile-editing tool — reading and messages only |
| Default geography | Warsaw + remote, moved into config | Geography, roles and filters change without touching code |
| Architecture | Hybrid: a Deep Agent orchestrator + a deterministic data-collection subgraph | Determinism where reliability and budget control are needed; agency where flexibility is needed |

### Rejected alternatives

- **A pure Deep Agent** (the LLM decides on its own what to search for and how much) — the cost per
  run floats, deduplication is unreliable, and the quality of requirement extraction depends on the model.
- **A rigid LangGraph pipeline with no agent** — does not support a dialogue of the form "take a
  closer look at this vacancy and rewrite the CV for it" without manual routing.
- **Guest/public sources only, without MCP** — noticeably less data, but this remains a degradation
  mode (§7) rather than the main path.

## 3. Stack

Python 3.12 (deepagents requires ≥3.11, the system has 3.10 — uv pins the version).

| Package | Version at design time | Role |
|---|---|---|
| `deepagents` | 0.7.13 | Agent harness: planning, filesystem, subagents, skills |
| `langgraph` | 1.2.11 | Data-collection subgraph, checkpoints |
| `langchain` | 1.3.18 | Models, structured output |
| `langchain-mcp-adapters` | 0.3.2 | Wiring the LinkedIn MCP in as a toolset |
| `langgraph-checkpoint-postgres` | 3.1.2 | `AsyncPostgresSaver` + `AsyncPostgresStore` |
| `langchain-openai` | 1.6.0 | The provider actually used behind `init_chat_model` and the embeddings for the Store index |
| `langchain-tavily` | 0.2.18 | Web search and page-content extraction |
| `psycopg[binary,pool]` | 3.2 | `langgraph-checkpoint-postgres` does not pull a driver of its own |
| `pydantic` | 2.9 | The schemas: `JobPosting`, `CandidateProfile`, `FitReport` |
| `pydantic-settings` | 2.15.0 | Secrets and connections out of `.env` |
| `pyyaml` | 6.0 | Reading `config/search.yaml` |
| `httpx` | 0.27 | The async client for the guest jobs endpoint |
| `selectolax` | 0.3.21 | Parsing the guest endpoint's HTML fragments |
| `pypdf` | 5.1 | Reading the source CV, and reading back the rendered PDF to check that its text extracts |
| `python-docx` | 1.1 | Reading a CV supplied as DOCX |

Versions are the floors declared in `pyproject.toml`, not upper pins.

Dev-only extra (`pip install -e ".[dev]"`), deliberately not a runtime dependency:
`langgraph-cli[inmem]` 0.4.31 for `langgraph dev` and Studio, plus `pytest` 8.3, `pytest-asyncio` 0.24
and `ruff` 0.8. The graph itself must be importable without the CLI installed, because phase 2 runs it
behind a shim rather than behind `langgraph dev`.

External services: OpenAI (key in hand), Tavily (key in hand), LangSmith (key in hand), Neon (needs setting up).
PDF rendering is Typst (`brew install typst`): a single binary, no wrestling with LaTeX.

## 4. Architecture

### 4.1 Three layers

**Data sources.** The LinkedIn MCP under the burner session; LinkedIn's guest jobs endpoint
(`jobs-guest/jobs/api/seeMoreJobPostings`, verified — it answers 200 without authorisation) for a
broad cheap scan; Tavily for researching companies, salary benchmarks and vacancies outside LinkedIn.

**Data and logic.** The deterministic `research_jobs` subgraph and storage on Neon.

**Dialogue.** A Deep Agent orchestrator with subagents.

### 4.2 The `research_jobs` subgraph

An ordinary `StateGraph`, exposed to the agent as a single tool. Five nodes:

1. **`scan`** — a broad search across the roles and locations from `config/search.yaml`, against the
   guest endpoint only (zero risk to the account, cheap). Tavily is **not** wired into the subgraph:
   it hangs off the orchestrator, the `job-analyst` and `company-researcher` subagents, and profile
   ingestion instead. The capability is therefore present, just not inside `scan` — venues outside
   LinkedIn are reached by the agent asking for them, not by every scan paying for them. A failing
   guest scan is not fatal: the node records a note and hands an empty list onwards.
2. **`dedupe`** — the canonical vacancy key: the LinkedIn job id, and in its absence a hash of the
   normalised `(company, title, location)`. Anything already in the Store is filtered out **before**
   spending tokens and requests against LinkedIn.
3. **`enrich`** — `get_job_details` over MCP only for new vacancies that passed the prefilter, and
   only within the call budget. The one and only place where we touch LinkedIn under the account at all.

   **The prefilter** is a cheap cull based on data we already have after `scan`, before spending a
   request against LinkedIn: location mismatch against the config, seniority outside the given range,
   a company or keywords on the stop-list from the `feedback` namespace, a vacancy older than the
   freshness window.
4. **`extract`** — raw description → the `JobPosting` Pydantic schema. Structured output, not free
   text. **The node runs with no tools at all** — this is the architectural defence against injection (§5).
5. **`persist`** — the full dossier goes into the Store, only a compact card is returned outwards.

### 4.3 Context economy (critical)

Full vacancy texts **never** reach the agent's main context. The subgraph hands back a list of cards
of a few lines each; the full dossier stays in the Store and is meant to be read by a subagent only
when genuinely needed — for example, when tailoring a CV to a vacancy. The compact output even ends
with a reminder to hand a vacancy id to `job-analyst` rather than pull the description upwards.
Without this rule the context burns out around the fifth vacancy.

Note that the subagents are told to read the dossier from memory but are given no tool that reads the
`jobs` namespace, so today they work from what the caller passes them. The rule above is the one that
matters and it holds; the retrieval side of it is unfinished.

### 4.4 Collecting the Candidate Profile

A separate tool, `bootstrap_profile` in `tools/profile_ingest.py`, run once on first use and on
command when the data needs refreshing:

1. **The CV file** — the user drops the file into `data/private/` (the default path lives in
   `config/search.yaml`), and the text is extracted from there. PDF, DOCX, Markdown and plain text
   are all accepted: the source of truth for the owner's own CV is as likely to be a `.md` file in
   this repository as an exported PDF, and refusing it would only invite a pointless conversion step.
2. **Public LinkedIn** — `get_person_profile` against the URL of the main (not burner) profile.
   From the burner account `get_my_profile` returns an empty shell, so what is used is precisely
   the reading of somebody else's public profile.
3. **The personal page** — the Tavily extraction tool (exposed as `web_extract`) against the URL.
4. **Merging** into the `CandidateProfile` schema, with a source reference on every claim.
5. **Filling the gaps** — the tool returns a list of what the sources did not cover (right to work,
   willingness to relocate, salary expectations) and the agent asks the user about exactly those.

The result goes into the `profile` namespace. Every claim carries its source — this is needed because
the scoring rubric requires evidence to be quoted (§10).

The file itself is read by Python inside the tool, not by the agent through its file tools:
`data/private/**` is denied to those (§5.3). Email and phone found in the CV are stripped before the
merge call and written to the private contacts file, so they reach the document only at render time
and never the model. The merge is a direct model call outside the agent's middleware, which is
precisely why the redaction is done explicitly here rather than left to the PII layer.

### 4.5 Subagents

| Subagent | Purpose | Tools |
|---|---|---|
| `job-analyst` | Deep analysis of a single vacancy | Filesystem, LinkedIn MCP (read), Tavily |
| `cv-writer` | Generating CVs and LinkedIn texts | Filesystem, `render_pdf`, the whole `skills/` directory |
| `company-researcher` | Context on the company | Tavily, `get_company_profile`, `get_company_employees` |

Each works in an isolated context and returns only the result upwards. The filesystem tools come from
the harness, which gives every subagent its own filesystem middleware; the `data/private` denial
(§5.3) is inherited by all of them.

Skills are passed to subagents explicitly — they are not inherited from the parent. What `cv-writer`
receives is the `skills/` directory as a whole rather than a hand-picked skill: the five skills
(`writing-cv-content`, `passing-ats-screening`, `designing-cv-documents`, `applying-in-poland-and-eu`,
`optimizing-linkedin-profile`) are cross-referencing and a CV task routinely needs three or four of
them at once. Which ones to read is stated in the subagent's prompt rather than enforced by the
wiring; the loader lists them, and the model pays only for what it opens.

### 4.6 The flow of a typical dialogue turn

```
user: "find vacancies"
  → agent: write_todos (plan)
  → tool research_jobs(config)
      → scan (guest jobs endpoint)
      → dedupe (against the Store)
      → enrich (LinkedIn MCP, under budget)
      → extract (Pydantic, no tools)
      → persist (Store)
      ← compact cards
  → tool score_jobs: the scoring.py rubric for each vacancy
  → answer: a table "vacancy — score — main gap"
           + a proposal for the next step
```

## 5. Security and middleware

Out of the box: `TodoListMiddleware`, `FilesystemMiddleware`, `SubAgentMiddleware`,
`SummarizationMiddleware`. Four of our own.

`HumanInTheLoopMiddleware` is **not implemented in phase 1** and is not in the stack. It was
foreseen for confirming actions with side effects, and phase 1 turned out to have none worth
confirming: the writing LinkedIn tools are absent rather than gated (§5.5), and the only thing the
agent writes is files inside the repository. A confirmation prompt in front of `write_file` would
train the user to click through prompts, which is worse than not asking. It returns when there is
something genuinely irreversible to approve.

### 5.1 `LinkedInBudget`

The main defence of the burner account. A hard ceiling on LinkedIn calls per run and per hour, jitter
between requests, exponential backoff on 429. When the limit is exhausted the tool returns a coherent
refusal to the agent, **not an exception** — the agent is obliged to carry on working on other sources.

### 5.2 `InjectionGuard`

Vacancy descriptions and web pages are untrusted input; "ignore previous instructions" may very well
be sitting in there. The defence has two levels:

- **Architectural (primary):** the `extract` node, which digests the raw text, has access to not a
  single tool — only structured output against the schema. There is nothing there for an injection to call.
- **Textual (secondary):** untrusted content is wrapped in delimiters with an explicit note saying
  "this is data, not instructions", and obvious injection patterns are stripped out.

Tools with side effects are unavailable at any step where untrusted content is processed.

### 5.3 `PIIRedaction`

Phone number and email from the CV do not travel into LangSmith traces. Placeholders live in
the prompts; the real values are substituted only at the PDF rendering stage. The email detector is
the stock one; the phone pattern is written by hand, because Polish and international formats are
what will actually appear, and because a false positive here is more expensive than a miss — it would
quietly corrupt figures like "400k documents" or "2021 - 2024" in the CV text.

Redaction alone is not enough, because the real values still sit in a file the agent could think to
open. So `data/private/**` is denied to the agent's filesystem tools outright, for read and for write,
at the top level and therefore for every subagent as well. The contacts file is read only by the PDF
renderer, in Python, outside the model's context. Without that denial the PII layer would protect
against everything except the one obvious move.

### 5.4 `CostGuard`

A ceiling on tokens and calls per single run: our own token accounting on top of the stock tool-call
and model-call limiters, all three ending the run gracefully so the agent can answer with what it has
already gathered. Plus model routing: the cheap model for extraction, summarisation and the analysis
subagents; the senior one for the orchestrator itself and for writing CVs. Fit scoring needs no model
at all — see §10.

### 5.5 The limits of what the agent can do

The agent is handed **only the read-only subset** of the LinkedIn MCP: `search_jobs`,
`get_job_details`, `get_recommended_jobs`, `get_person_profile`, `get_company_profile`,
`get_company_employees`, `search_people`.

`send_message` and `connect_with_person` **are not included in the toolset at all** — they are not
hidden behind a confirmation, they are absent. An agent capable of writing to people on the user's
behalf is a separate class of risk that needs a design of its own.

The filter is an **allowlist, not a denylist**. Naming the two forbidden tools and letting everything
else through would mean the day the MCP server ships a new writing tool, that tool arrives in the
agent's hands by default and nobody notices. Anything not on the list is dropped and logged, so a new
capability has to be admitted deliberately. The forbidden names are also written down separately,
purely so that a refusal is legible in logs and assertable in tests.

The same reasoning governs the file tools. The agent's `FilesystemMiddleware` is built by hand with an
explicit list — `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep` — rather than taken as the
harness default, because that is the only way to withhold `execute`. Running arbitrary shell commands
is needed for none of this agent's tasks, and the cost of one mistake is out of all proportion to the
convenience. `delete` is left out on the same grounds.

### 5.6 Secrets

`pydantic-settings` + a `.env` that is in `.gitignore`. Only `.env.example` is in the repository.
Keys never end up in `langgraph.json`.

## 6. Memory (Neon Postgres)

- `AsyncPostgresSaver` — thread checkpoints (dialogue history).
- `AsyncPostgresStore` with an index on `text-embedding-3-small` (1536 dims) — long-term memory with
  semantic search across threads.

### The in-memory fallback

Neon is the target, but it is not a precondition for the agent starting. When `SCOUT_DATABASE_URL` is
unset, and also when it is set but Postgres cannot be reached, `memory.py` falls back to an in-process
store and saver and says so in the log. This is not a test stub: the agent had to be runnable and
useful before an external service existed, and a developer who has to provision a database before
seeing the first answer will not see the first answer. What is lost is persistence between runs, which
degrades dedup rather than breaking it — the same trade as everywhere else in §7.

The embedding index is dropped when there is no OpenAI key, for the same reason: no key means no
embeddings, and an unindexed store that works beats a configured store that refuses to open.

### Namespaces

| Namespace | Contents | Purpose |
|---|---|---|
| `("profile", user_id)` | Candidate Profile | The source of truth about the user, versioned |
| `("jobs", user_id)` | Vacancy dossiers, key = canonical id | Dedup and history |
| `("companies",)` | Cache of company research with a TTL | Do not research the same thing twice |
| `("artifacts", user_id)` | CVs, letters, LinkedIn texts | The history of what has been generated |
| `("taxonomy",)` | A living document about the track's requirements | Feeds the prompt, the scoring and the gap analysis |
| `("feedback", user_id)` | The user's reactions to vacancies | Influences the prefilter and the scoring |

`taxonomy` is read but never written in phase 1: the loader, the schema and the prompt layer that
consumes it all exist, and nothing fills them, because the mode that would is not built (§8). The
prompt layer handles the empty case explicitly rather than pretending.

In phase 1 the system is single-user: `user_id` is a constant from the config. The namespaces are
parameterised by it anyway, so that phase 3 (a widget on the site with several visitors) does not
require reworking the storage schema.

**`feedback` deserves particular attention.** When the user says "this is too senior" or "I do not
want to go to that company", it is written into memory and changes the prefilter and the scoring of
subsequent runs. Without this the agent will bring back the same rubbish every time.

### An operational wrinkle with Neon

The free tier puts the compute to sleep. The first connection after a pause is cold (several seconds),
so the connection pool is configured with retry from the outset — otherwise the first request of the
day looks like a breakage.

## 7. Degradation and error handling

| Situation | Behaviour |
|---|---|
| The LinkedIn session has gone stale | Switch to the guest source + Tavily, with an honest note in the answer about the incompleteness of the data and an instruction to log in again |
| 429 from LinkedIn or the guest endpoint | Backoff, then switch source |
| The LinkedIn call budget is exhausted | The tool returns a refusal, the agent carries on with other sources |
| Neon cold start | Retry in the connection pool |
| No database URL, or Postgres unreachable | Fall back to the in-process store and saver; the run works, nothing survives it |
| The Store is missing altogether at `persist` | Return the cards anyway, with a note that dedup will be worse next time |
| No OpenAI key | The `extract` node returns the postings unparsed with a note; the Store index is built without embeddings |
| Tavily is unavailable | Work on LinkedIn data only, with a note |

The general principle: **a partial result with an honest caveat beats a crash.**

## 8. Skills research as a function of the agent

**Not implemented in phase 1.**

The "Agentic SDLC Engineer" role is too new to hard-wire its requirements into code — in six months
that would be untrue. Hence a separate **`bootstrap_taxonomy`** mode:

1. Collect 30-50 vacancies on the track and adjacent roles.
2. Run them through `extract`.
3. Cluster the requirements by frequency: the core (appears in the majority of vacancies), the
   periphery, signal skills.
4. Save into the `taxonomy` namespace.

The result feeds the system prompt, the scoring and the gap analysis. Refreshed on the user's command.

What exists today is only the scaffolding around the hole: the `Taxonomy` and `SkillDemand` schemas,
the load and save helpers in `memory.py`, the tuning keys under `taxonomy:` in `config/search.yaml`
(`bootstrap_target`, `core_threshold`, `peripheral_threshold`), and the prompt layer that renders the
taxonomy when it is there. Nothing calls the save helper, so the namespace stays empty and the prompt
falls back to a line inviting the user to run the mode. **That line is currently a promise the code
does not keep** — it is the first thing to fix when this section gets built.

Note also that `gap_analysis` (§10) already answers most of the same question straight from the corpus
of stored postings, without a taxonomy. What the taxonomy adds is a view that survives between runs and
feeds the prompt, which is why it is still worth building rather than quietly dropping.

## 9. System prompt

Assembled out of layers rather than written as one wall of text:

1. Role and behavioural contract
2. The ban on inventing experience (below), placed second because it outranks everything after it
3. Rules of context economy (read dossiers via files, do not drag them in wholesale)
4. Rules for handling untrusted content
5. The scoring rubric, with the weights and thresholds interpolated from the config so the prompt
   cannot drift away from what `scoring.py` actually computes
6. When to go and read a skill
7. The answer format
8. **A dynamic insertion** of the current taxonomy from memory

### A hard rule: no inventing experience

Not in the assessment, and above all not in the CV. If a skill is not in the Candidate Profile, it is
not in the CV. The agent may propose rephrasing existing experience in the language of the vacancy,
but not inventing new experience. This is a defence against a résumé the user would be unable to
defend at interview.

## 10. The fit-score rubric

**A gate on the hard requirements** — location, visa, language, required years of experience. It is
not one of the weighted components and carries no weight of its own: it is a ceiling applied after the
weighted score is computed. Fails it → the score is capped from above at `hard_gate_fail_cap` and the
vacancy is honestly flagged, not pulled up to a pretty number. The gate only ever fires on facts that
are actually known; an unknown is not a failure, because letting a vacancy through is more honest than
rejecting it on a guess.

Four weighted components, whose weights sum to 100:

1. **`must_have_overlap`** — overlap on must-have skills; every match is obliged to **quote a specific
   line** from the Candidate Profile. No evidence, no points.
2. **`transferable`** — transferable skills, reached through an explicit adjacency map, with a
   reducing coefficient.
3. **`signals`** — how much of the posting's declared tech stack the profile already covers.
4. **`seniority_fit`** — the distance between the level the posting asks for and the level the
   profile's years imply. A direct hit scores full, one step away scores half, further away scores
   nothing. An unknown level on either side scores full rather than punishing the vacancy.

Output: 0-100 and one of three categories — *apply now*, *apply once a specific gap is closed*, *pass*.
The category thresholds, the four weights, the transferable coefficient and the hard-gate cap all live
in `config/search.yaml` rather than in code: they will have to be calibrated after the fact, looking at
real results.

The deterministic part of the rubric lives in `scoring.py` and is covered by unit tests.
The LLM is responsible only for the qualitative part with its quoted evidence.

### Aggregated gap analysis

A separate output on top of the whole corpus of vacancies: "LangGraph is required in 8 of the 12
vacancies on the track and you do not have it — priority number one". It answers not the question
"where do I apply today" but "what do I do over the next month".

## 11. Repository structure

```
agentic-sdlc-scout/
├── pyproject.toml            # uv, python 3.12
├── langgraph.json            # langgraph dev / Studio right away
├── .env.example
├── config/search.yaml        # roles, geo (Warsaw), filters, limits, weights
├── data/private/             # source CV and real contacts; denied to the agent (§5.3)
├── out/                      # rendered PDFs
├── skills/
│   ├── applying-in-poland-and-eu/SKILL.md
│   ├── designing-cv-documents/SKILL.md
│   ├── optimizing-linkedin-profile/SKILL.md
│   ├── passing-ats-screening/SKILL.md
│   └── writing-cv-content/SKILL.md
├── src/scout/
│   ├── main.py               # CLI: one-shot and REPL, the thin transport
│   ├── agent.py              # assembling create_deep_agent
│   ├── prompts.py            # system prompt layers
│   ├── config.py             # pydantic-settings + loading search.yaml
│   ├── schemas.py            # JobPosting, CandidateProfile, FitReport
│   ├── memory.py             # store/saver with in-memory fallback, namespaces
│   ├── scoring.py            # the rubric, deterministic part
│   ├── middleware/
│   │   ├── linkedin_budget.py
│   │   ├── injection_guard.py
│   │   ├── pii.py
│   │   └── cost_guard.py
│   ├── tools/
│   │   ├── linkedin_mcp.py
│   │   ├── guest_jobs.py
│   │   ├── tavily.py
│   │   ├── profile_ingest.py # bootstrap_profile
│   │   ├── analysis.py       # score_jobs, gap_analysis, remember_preference
│   │   └── render_pdf.py
│   └── graphs/research.py    # the scan→dedupe→enrich→extract→persist subgraph
└── tests/
    ├── fixtures/guest_jobs_sample.html
    ├── test_guest_jobs.py
    ├── test_render.py
    ├── test_research_graph.py
    ├── test_safety.py
    └── test_scoring.py
```

The skills are cut by topic rather than by consumer — there is no `cv-writing` skill, there are five
skills about ATS screening, CV content, document design, LinkedIn and the Polish and EU specifics,
and a single CV task usually needs several of them. Fit analysis is not a skill at all: its
deterministic half is `scoring.py` and its qualitative half is a prompt layer, neither of which is
something the model should be reading as prose.

The principle: every module small and with a single responsibility. A file growing is a signal that
it is doing too much.

## 12. Testing

- **Units without an LLM** on dedup, normalisation and scoring — these are deterministic, and that is
  exactly where the galling bugs will be.
- **Recorded fixtures** where the input is markup we do not control.

What that came out as, five files under `tests/`:

| File | What it holds the line on |
|---|---|
| `test_guest_jobs.py` | The guest-endpoint parser against recorded HTML, and the seniority guess. The most fragile part of the system: LinkedIn changes its markup without warning |
| `test_research_graph.py` | The prefilter, card formatting, and the subgraph's node and edge wiring |
| `test_scoring.py` | The deterministic rubric |
| `test_safety.py` | The toolset boundaries, injection neutralisation, contact redaction and the `data/private` denial |
| `test_render.py` | Markdown to Typst, and — where Typst is installed — reading the text back out of the built PDF |

Only the guest HTML is recorded as a fixture; MCP and Tavily responses are not, because nothing in
phase 1 tests their parsing — those tools are passed through to the model rather than interpreted.

### Not yet written

**Not implemented in phase 1.** Both of the following are still wanted, and neither exists:

- **A LangSmith eval** on requirement extraction: a small labelled set of vacancies. This is the one
  untested seam that matters — everything downstream of `extract` is unit-tested, and `extract` itself
  is a model call whose quality nothing currently measures.
- **One end-to-end smoke test** against live LinkedIn under a separate pytest marker, not in CI. The
  `live` marker is declared in `pyproject.toml` and no test wears it yet.

## 13. Groundwork for phases 2 and 3

`langgraph.json` is laid down straight away: locally it gives Studio via `langgraph dev`, and for a
later deployment it is the same graph in a container.

**Phase 2 (OpenWebUI):** a thin OpenAI-compatible `/v1/chat/completions` shim over `graph.astream`.
The agent stays transport-independent.

**Phase 3 (widget on the personal page):** the same shim, but with authentication mandatory and a
separate read-only mode. Otherwise the very first visitor to the site gets access to the user's
profile, their memory and the LinkedIn burner session.
