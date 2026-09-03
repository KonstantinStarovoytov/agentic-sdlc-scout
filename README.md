# Agentic SDLC Scout

An agent that researches open vacancies on the Agentic SDLC Engineer track,
scores how well your profile fits them, and drafts a CV or LinkedIn text when
you ask for one. Built on LangGraph and DeepAgents.

It answers three questions: what is open right now, how close you actually are,
and what to learn next.

## How it works

A Deep Agent orchestrator holds the conversation and delegates. Data collection
lives in a deterministic subgraph the agent sees as one tool, which keeps the
cost of a run predictable and the number of LinkedIn requests bounded.

```
scan -> dedupe -> enrich -> extract -> persist
```

Only compact cards come back to the agent; full descriptions stay in the store
and are read by a subagent when a specific vacancy needs a deep read.

Scoring is deterministic and lives in `scoring.py`, not in a prompt. Every skill
match must quote a line from your Candidate Profile; a skill without a quote
scores nothing, and failing the hard gate (location, right to work, language,
required years) caps the score instead of being averaged away.

| Component | What it does |
|---|---|
| `graphs/research.py` | The collection subgraph, exposed as `research_jobs` |
| `scoring.py` | The rubric: hard gate, must-have overlap, transferables, signals |
| `tools/profile_ingest.py` | Builds the Candidate Profile from CV, LinkedIn and personal site |
| `tools/render_pdf.py` | Markdown to Typst to PDF, then verifies the text extracts |
| `middleware/` | LinkedIn budget, injection guard, PII redaction, cost control |
| `skills/` | Verified guidance on ATS, CV content, layout, Poland/EU rules, LinkedIn |

Sources: the LinkedIn guest endpoint (unauthenticated, cheap), an optional
LinkedIn MCP server under a burner account, and Tavily for everything else.

## Safety

These are structural properties, not prompt instructions:

- **No write access to LinkedIn.** Messaging and connection tools are filtered
  out by an allowlist rather than gated behind a confirmation.
- **No shell.** The `execute` and `delete` filesystem tools are not in the toolset.
- **Injection defence.** Descriptions are digested in a node with no tools at
  all; wrapping and pattern neutralisation are a second layer, not the first.
- **PII stays local.** Email and phone are redacted before any model call and
  live in `data/private/`, which the agent's filesystem tools cannot reach. They
  are substituted into the document at render time.
- **Budgets.** Per-run and per-hour LinkedIn call limits, token and tool-call
  ceilings. Exceeding one returns a refusal the agent can work around, not a crash.

## Setup

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and
[Typst](https://typst.app) 0.14+ for PDF rendering (`brew install typst`).

```bash
uv sync --extra dev
cp .env.example .env   # then fill in the keys
```

`OPENAI_API_KEY` is the only required key. `TAVILY_API_KEY` enables web search,
`LANGSMITH_API_KEY` enables tracing, and `SCOUT_DATABASE_URL` (Neon Postgres)
enables persistent memory — without it the agent runs in memory and forgets
everything on restart.

Put your CV at `data/private/cv.pdf` (PDF, DOCX, MD or TXT all work).

The LinkedIn MCP server is optional and needs two things beyond
`SCOUT_LINKEDIN_MCP_COMMAND`. Authenticate once with
`mcp-server-linkedin --login` while signed in to the burner account — there is
no cookie to paste, the session is a browser profile under `~/.linkedin-mcp/`.
And include `--no-auto-import` in the command: without it the server adopts the
LinkedIn session of any locally signed-in Chromium browser, which is your real
profile, so the agent refuses to start it. Skipping all of this is fine; the
agent then runs on the guest endpoint and Tavily and says so in its answers.

## Usage

```bash
uv run scout "find AI engineer roles in Warsaw and tell me where I stand"
uv run scout                      # interactive REPL
uv run scout --thread cli-1234    # continue an earlier conversation
```

Start with `bootstrap_profile` — until the Candidate Profile exists, the agent
refuses to score, because a score without a profile would be invention.

Inspect the graphs locally with `uv run langgraph dev`.

## Configuration

`config/search.yaml` holds everything you would otherwise edit in code: roles,
locations, freshness window, prefilter stop-lists, budgets, rubric weights and
verdict thresholds.

## Development

```bash
uv run pytest -m "not live"   # tests
uv run ruff check src tests   # lint
uv run mypy                   # types
uv run tox                    # all of the above
pre-commit install            # run the checks on every commit
```

Sources, comments, commits and docs are English-only; `scripts/check_ascii.py`
enforces it in the pre-commit hook and in CI.

## Documentation

- `docs/superpowers/specs/` — the design document behind these decisions
- `docs/research/` — sourced research on ATS, CV writing and LinkedIn, with links
- `skills/` — the operational rules the agent reads before writing a CV
