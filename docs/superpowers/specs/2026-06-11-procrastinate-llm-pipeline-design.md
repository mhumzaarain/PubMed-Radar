# Procrastinate + LLM Summarization Pipeline — Design

**Date:** 2026-06-11
**Status:** Approved
**Phase:** 1 of the post-restructure roadmap (see Context)

## Context

PubMed Radar's Week-1 backend is complete: Django 5.1 + DRF + PostgreSQL, JWT auth
(`apps/users`), Radar CRUD (`apps/radars`), Paper/PaperRadar/AISummary/UserPaperAction
models and read API (`apps/papers`), and a working PubMed E-utilities client
(`services/pubmed_client.py`). `fetch_radar()` works end-to-end but runs synchronously
inside the HTTP request, and nothing populates `AISummary`.

Project-direction decisions made during brainstorming (recorded here, implemented in
later phases):

- **Frontend:** Django templates + vanilla JS — no React, no separate SPA.
- **Auth:** will switch from JWT to Django session auth; DRF endpoints stay and are
  called by page JS with `fetch()` + CSRF token. SimpleJWT will be dropped (Phase 2).
- **Background tasks:** Procrastinate (PostgreSQL-backed, no Redis/broker), replacing
  the spec's original Celery plan.
- **LLM:** any OpenAI-compatible endpoint, configured via `.env` — works with OpenAI,
  Ollama, LM Studio, vLLM, OpenRouter, and Anthropic's compatibility endpoint.

**This phase (1):** Procrastinate worker + periodic scheduling, the LLM summarizer
service, and the fetch → summarize → store pipeline.
**Later phases:** (2) session-auth switch + template/static skeleton, (3) dashboard UI
(feed, radar management, paper detail, filters, search), (4) exports, digest, analytics.

## Architecture (Approach A: event-driven chain with periodic dispatcher)

Procrastinate periodic tasks are static cron definitions, so per-radar schedules are
implemented with a single hourly dispatcher that reads the database:

```text
cron (hourly)
  └─ dispatch_due_radars            finds active radars due per schedule
       └─ fetch_radar_task(radar)   PubMed search + store papers
            └─ summarize_paper_task(paper)   one per unsummarized paper → AISummary
```

Alternatives considered: independent periodic sweeps (decoupled but summaries lag and
DB is polled for what the chain delivers as events) and a hybrid chain + catch-up sweep
(second code path for the same job; retries plus re-defer-on-next-fetch already cover
its failure cases). Chain chosen.

## Procrastinate integration

- Add `procrastinate` dependency; put `procrastinate.contrib.django` in
  `INSTALLED_APPS`. Its job-queue tables ship as Django migrations and are created by
  ordinary `manage.py migrate`. Jobs live in the same PostgreSQL database.
- **Driver swap:** Procrastinate requires psycopg 3. Replace `psycopg2-binary` with
  `psycopg[binary]` (Django 5.1 supports it natively; no settings change).
- **Worker:** new `worker` service in `docker-compose.yml` — same image as `web`,
  command `python manage.py procrastinate worker`, same `env_file`,
  `depends_on: db` (healthy).

## Tasks

### `apps/radars/tasks.py`

1. **`dispatch_due_radars`** — periodic, cron `0 * * * *`. Selects active radars where
   `last_fetched_at` is null, or older than 24 h (`daily`) / 7 days (`weekly`). Defers
   `fetch_radar_task` for each.
2. **`fetch_radar_task(radar_id)`** — wraps the existing `fetch_radar()` function,
   which stays a plain callable. After storing papers it defers `summarize_paper_task`
   for **every paper in this radar with a non-empty abstract and no `AISummary`** —
   not just newly created ones. This re-defer-on-next-fetch behavior is what makes the
   pipeline self-healing without a sweep task.
   `queueing_lock=f"fetch-radar-{radar_id}"` prevents double-queuing the same radar.
   Retry: 3 attempts, exponential backoff. Catches `Radar.DoesNotExist` (radar deleted
   between dispatch and execution) and exits cleanly without retry.

### `apps/papers/tasks.py`

1. **`summarize_paper_task(paper_id)`** — idempotent: returns immediately if an
   `AISummary` exists. Otherwise calls `services.summarizer.summarize(paper)` and
   creates the row. Retry: 5 attempts, exponential backoff (LLM rate limits, transient
   malformed output).

### API change

`POST /api/radars/{id}/fetch/` defers `fetch_radar_task` and returns
`202 Accepted` with `{"status": "queued"}` instead of running synchronously.

### Concurrency & rate limits

When multiple radars are due, the dispatcher queues all their fetch jobs at once, but
the worker runs with default concurrency (one job at a time), so fetches — and the
summarize jobs they spawn — execute sequentially. This is deliberate: PubMed allows
only 3 requests/second without an API key, and sequential execution also naturally
rate-limits LLM calls (relevant for free tiers and local models). Each radar fetch
costs 2 PubMed requests (esearch + efetch) and ingests at most 100 papers
(`max_results=100`). Worker concurrency can be raised later via
`procrastinate worker --concurrency=N` if throughput ever becomes a problem.

## LLM summarizer service

`services/summarizer.py` exposes `summarize(paper) -> dict`, using the `openai`
package as a generic client for any OpenAI-compatible endpoint.

Configuration (`.env`, read via `python-decouple` in `config/settings.py`):

| Variable | Meaning | Example |
| --- | --- | --- |
| `LLM_BASE_URL` | OpenAI-compatible endpoint | `https://api.openai.com/v1`, `http://localhost:11434/v1` |
| `LLM_API_KEY` | API key (dummy string OK for local servers) | `sk-...` |
| `LLM_MODEL` | Model name, passed through | `gpt-4o-mini`, `llama3.1` |
| `LLM_TIMEOUT` | Request timeout in seconds | `60` (default) |

Prompt: the structured-extraction prompt from the project spec (title + journal +
abstract → JSON with `one_line_summary`, `key_findings`, `methodology`,
`relevance_score`, `novelty_tag`).

Parsing rules:

- Strip markdown code fences before `json.loads`.
- Invalid JSON → raise `SummarizationError` (task retry re-samples the model).
- Clamp `relevance_score` to 1–5.
- `novelty_tag` not in the six allowed choices → raise `SummarizationError`.
- Missing methodology fields → stored as null.
- `AISummary.model_used` = `LLM_MODEL`.

Papers with empty abstracts are never deferred for summarization (filtered in
`fetch_radar_task`), so they produce neither noise summaries nor eternal retries.

## Config & infrastructure changes

- `config/settings.py`: add `procrastinate.contrib.django` to apps; add the four
  `LLM_*` settings.
- `.env.example`: add `LLM_*` variables with OpenAI and Ollama examples.
- `docker-compose.yml`: add the `worker` service.
- `pyproject.toml`: add `procrastinate`, `openai`; swap `psycopg2-binary` →
  `psycopg[binary]`.

## Error handling

- **Transient** (PubMed 5xx, LLM rate limits, malformed JSON): Procrastinate retries
  with exponential backoff (3× fetch, 5× summarize).
- **Permanent**: job lands in `failed` state (inspectable via admin /
  `manage.py procrastinate`); the paper is re-deferred on the radar's next scheduled
  fetch.
- **Idempotency**: `get_or_create` for Paper/PaperRadar, existence check in
  `summarize_paper_task`, `queueing_lock` on fetch.

## Testing

- **Summarizer unit tests** (`services/tests/test_summarizer.py`), OpenAI client
  mocked: clean JSON, fenced JSON, invalid JSON (raises), out-of-range score
  (clamped), bad novelty tag (raises).
- **Task tests** with Procrastinate's in-memory test connector (assert deferrals
  without a worker): dispatcher selects exactly the due radars (daily overdue, weekly
  not-yet-due, inactive excluded, never-fetched included); fetch task defers summarize
  only for unsummarized papers with abstracts; summarize task creates the row and
  skips when one exists.
- **View test**: `POST /fetch/` returns 202 and defers the job (replaces the current
  synchronous assertion).
- Existing PubMed client and `fetch_radar()` tests keep passing unchanged.
