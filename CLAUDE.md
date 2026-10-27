# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Concourse** — multi-platform deadline/schedule aggregation service. Each platform has an isolated fetcher that scrapes data and emits normalized `ScheduleEventCreate` objects. A FastAPI backend aggregates these into SQLite, exposes a REST API, and drives an agent-friendly endpoint. A CLI (`concourse`) handles day-to-day operations. Vue 3 frontend is planned.

## Commands

```
uv sync                                           # install / sync deps
uv run uvicorn backend.main:app --reload          # dev server (port 8000)
uv run pytest                                     # full test suite
uv run pytest tests/test_scholat_parser.py -v     # single file
uv run python -m fetchers.codeforces              # run a fetcher standalone
uv run python -m fetchers.scholat --save-credentials
concourse list                                    # after uv sync + uv pip install -e .
```

Frontend (Vue 3 + Vite, not yet scaffolded):
```
npm run dev / npm run build / npm run type-check
```

## Directory structure

```
shared/
  models.py        ScheduleEventCreate, Event, StagedEvent, compute_content_hash
  credentials.py   DPAPI read/write (pure ctypes, no pywin32)
  config.py        load config.yaml + .env secrets via pydantic-settings
fetchers/
  base.py          Fetcher Protocol (runtime_checkable)
  codeforces.py    pure-HTTP reference fetcher (no login)
  scholat.py       Playwright fetcher + parse_homework_list/detail pure fns
backend/
  db.py            SQLModel async engine + init_db()
  repository.py    upsert_event, list_events, staged CRUD
  scheduler.py     APScheduler cron wrapper around fetchers
  main.py          FastAPI app, routes, lifespan (starts scheduler)
  services/
    agent.py       Anthropic tool-use loop, action whitelist
concourse/
  cli.py           argparse CLI: list/add/staged/accept/dismiss/fetch/creds
tests/
  test_cli_time.py      parse_shorthand unit tests
  test_scholat_parser.py  parse_homework_list/detail offline tests
config.yaml        non-secret config (fetcher params, cron, agent whitelist)
.env               secrets (DATABASE_URL, AGENT_TOKEN, ANTHROPIC_API_KEY)
```

## Architecture

### Data model

`ScheduleEventCreate` is the fetcher output contract. `Event` is the persisted form (SQLite, naive UTC datetimes). `StagedEvent` holds agent/CLI proposals pending human accept/dismiss. Unique key is `(platform, source_id)`. Upserts compare `content_hash` (sha256 of normalised fields) to detect changes.

All datetimes stored as naive UTC. `to_naive_utc` / `to_aware_utc` helpers in `shared/models.py` handle conversion at boundaries.

### Fetcher contract

Every fetcher implements `Fetcher` (Protocol in `fetchers/base.py`):
```python
class MyFetcher:
    name = "myplatform"
    async def fetch(self, since=None) -> list[ScheduleEventCreate]: ...
```

`scheduler.py` discovers fetchers by name via `importlib.import_module("fetchers.<name>")` and instantiates `<Name>Fetcher(**config_kwargs)`. Adding a platform = one file + one entry in `config.yaml`.

**Playwright fetchers** use `launch_persistent_context` to preserve login sessions across runs (`.browser-data/<platform>/`). Scraping logic is split: `scrape` navigates and fetches HTML; `parse_*` are pure functions on HTML strings — the latter are unit-testable offline. See `fetchers/scholat.py` as the reference.

**HTTP fetchers** use `httpx.AsyncClient` with no browser. See `fetchers/codeforces.py`.

### Credential storage (DPAPI)

`shared/credentials.py` — pure ctypes, no pywin32. Payload is any JSON dict (username+password, tokens, etc.). Stored at `%LOCALAPPDATA%\concourse\credentials\<platform>.dpapi`. Bound to the current Windows user; cannot be decrypted on another machine or account. Non-Windows falls back to chmod-600 plaintext with a warning.

CLI: `concourse creds set <platform>` / `concourse creds forget <platform>`

### Agent endpoint

`POST /agent` requires `Authorization: Bearer <AGENT_TOKEN>`. Runs an Anthropic tool-use loop. Allowed actions are declared in `config.yaml agent.allowed_actions`; any tool call not in that list is rejected before dispatch. Write operations (`draft_add_event`) only produce `StagedEvent` proposals — they never write directly to `events`. All staged entries require explicit `accept` via `/staged/{id}/accept` or `concourse accept <id>`.

### CLI time shorthand

`mmdd+` = that day 23:59 CST → UTC (deadline end-of-day).  
`mmdd-` = that day 00:00 CST → UTC (start-of-day marker).  
Bare `mmdd` (no suffix) is rejected to avoid ambiguity.  
Full ISO 8601 strings are also accepted.

## Key decisions

- **No cross-platform deduplication** — each event is its platform's record; the aggregated view shows all platforms side-by-side without merging.
- **SQLite first** — no Docker for local dev. Switch to PostgreSQL: change `DATABASE_URL` to `postgresql+asyncpg://...` and `uv add asyncpg`.
- **DPAPI single-machine** — intentional for Windows Server home deployment over Tailscale. If porting to Linux, swap to `keyring` library.
- **Staged buffer for all writes** — agent and CLI never write directly to `events`; every addition goes through `staged_events` → human confirm.

## Environment variables

```
DATABASE_URL=sqlite+aiosqlite:///./concourse.db
AGENT_TOKEN=<long random secret>
ANTHROPIC_API_KEY=sk-ant-...
```

Copy `.env.example` → `.env`. `shared/config.py` loads them via `pydantic-settings`.
