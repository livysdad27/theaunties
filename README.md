# theAunties

**Autonomous Research Agents That Watch the World So You Don't Have To**

*Inspired by Ainsley Lowbeer — the entity in William Gibson's Jackpot trilogy who quietly monitors everything, understands context deeply, and intervenes only when it matters.*

---

## What It Does

You describe what you want to know about in plain language. An agent picks it up, finds real data sources (APIs, public datasets, government feeds), monitors them on a schedule, and delivers a daily research document — sourced, cited, and grounded in real data. No hallucination. No fluff.

**Example:**
```
You: I'm going fishing at Lake Travis this weekend — keep me updated on conditions
Agent: Creates topic, discovers NWS weather API + USGS water data, starts daily monitoring
You: (next morning) Get a research digest with water temperature, wind speed, and water levels
```

## Quick Start

### Prerequisites

- Python 3.12+
- API keys (optional — the system runs with stubs for testing)

### Setup

```bash
git clone <repo-url>
cd theaunties

# One-command setup: creates venv, installs deps, runs tests
./setup.sh
```

Or manually:

```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
source venv/Scripts/activate    # Windows (Git Bash)

pip install -r requirements.txt
```

### Configure

Copy `.env.example` to `.env` and edit:

```bash
cp .env.example .env
```

| Variable | Purpose | Required |
|----------|---------|----------|
| `GEMINI_API_KEY` | Google Gemini API for source discovery | For production |
| `ANTHROPIC_API_KEY` | Anthropic Claude API for synthesis | For production |
| `WEB_SEARCH_API_KEY` | Brave Search API for finding data sources | For production |
| `GOOGLE_DRIVE_CREDENTIALS_PATH` | Service account JSON for doc delivery | For production |
| `GOOGLE_DRIVE_FOLDER_ID` | Target Drive folder for daily docs | For production |
| `USER_EMAIL` | Email to share docs with | For production |
| `USE_STUBS` | Set `true` to run with canned responses (no API keys needed) | No (default: `true`) |

### Run

**Interactive chat (primary interface):**

```bash
python -m theaunties chat
```

**FastAPI server with scheduler:**

```bash
python -m theaunties serve
```

The server runs on `http://127.0.0.1:8000` (localhost only).

### Run Tests

```bash
python -m pytest
```

All 150 tests run with stubs — no API keys or external services needed.

## How It Works

### 1. Topic Setup (Chat)

Describe what you want to track in natural language. The agent parses your intent, confirms its understanding, and sets up a research topic.

### 2. Source Discovery

The agent uses an LLM to brainstorm relevant data sources, searches the web for public APIs and datasets, then validates each one with a test request. Only sources that return real, parseable data are registered.

All discovered URLs are validated for safety: HTTPS only, no private IPs, no localhost, no internal hostnames.

### 3. Scheduled Research Runs

Each topic runs on a cron schedule (default: daily at 6:00 AM). On each run:

1. Load accumulated context for the topic
2. Collect fresh data from all registered sources
3. Compare against previous run to detect changes
4. Summarize findings with source citations
5. Generate a daily research document
6. Update context for the next run

### 4. Daily Research Document

Each document follows a consistent structure:

- **Summary** — 2-3 sentence overview
- **What Changed** — specific changes since last run with before/after values
- **Detailed Findings** — organized by source, every claim cited
- **Sources** — status table showing which sources succeeded/failed
- **Agent Notes** — observations about data quality, gaps, or suggested adjustments

### 5. Context Accumulation

The agent doesn't start fresh every day. It maintains a rolling context per topic:
- Full detail for the last 7 days
- Older findings compressed into a cumulative summary
- User clarifications and detected trends preserved

## Architecture

```
theaunties/
├── theaunties/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Environment config (pydantic-settings)
│   ├── agent/
│   │   ├── core.py          # Research pipeline orchestrator
│   │   ├── discovery.py     # Source discovery + URL validation
│   │   ├── collector.py     # Data collection from sources
│   │   ├── analyzer.py      # Change detection + data analysis
│   │   └── context.py       # Per-topic context manager
│   ├── llm/
│   │   ├── router.py        # LLM routing (Gemini for discovery, Claude for synthesis)
│   │   ├── gemini.py        # Gemini client (stub + real)
│   │   └── claude.py        # Claude client (stub + real)
│   ├── output/
│   │   └── gdrive.py        # Doc generator (local Markdown + Google Drive)
│   ├── chat/
│   │   ├── handler.py       # Chat message routing + topic lifecycle
│   │   └── cli.py           # Rich terminal client
│   ├── scheduler/
│   │   └── manager.py       # APScheduler cron management
│   ├── db/
│   │   ├── models.py        # SQLAlchemy models
│   │   └── database.py      # DB engine + session factory
│   └── prompts/             # All LLM prompt templates
├── tests/                   # 150 tests, all runnable with stubs
├── data/                    # Runtime: SQLite DB, context files, docs
├── setup.sh                 # One-command setup
├── .env.example             # Config template
└── requirements.txt         # Pinned dependencies
```

## API Endpoints

When running with `python -m theaunties serve`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat` | Send a chat message (topic setup, refinement, Q&A) |
| `GET` | `/topics` | List all topics |
| `GET` | `/topics/{id}/status` | Get topic status, source count, last/next run |
| `POST` | `/topics/{id}/run` | Trigger an immediate research run |

## Anti-Hallucination

Every claim in the daily doc must be traceable to a real data source:

- The LLM is never asked to "tell me about X" — it summarizes collected data
- Every factual claim requires an inline source citation
- Facts and inferences are separated into distinct sections
- Sources are validated before registration
- Failed sources are flagged, not silently dropped
- All LLM calls are logged for auditability

## Current Status

**MVP (v0.1)** — Single agent, single topic, daily output, chat-based setup.

Running with **stub implementations** for LLM clients, web search, and Google Drive. The full pipeline works end-to-end with canned responses. To go live:

1. Implement real Gemini client in `llm/gemini.py`
2. Implement real Claude client in `llm/claude.py`
3. Implement Google Drive doc generator in `output/gdrive.py`
4. Add a real web search client (Brave Search API)
5. Set `USE_STUBS=false` in `.env`

## Tech Stack

- **Python 3.12+** with async/await throughout
- **FastAPI** — internal API server
- **APScheduler** — cron-style scheduling
- **SQLAlchemy** — ORM with SQLite
- **Rich** — terminal UI formatting
- **httpx** — async HTTP client
- **pydantic-settings** — typed configuration

## License

Private — not yet open source.

---

*theAunties: "She sees everything. She tells you what matters."*
