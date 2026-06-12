# Dashboard UI + Paper API Filters — Design

**Date:** 2026-06-12
**Status:** Approved
**Phase:** 3 (Phase 1: Procrastinate + LLM pipeline; Phase 2: session auth + frontend skeleton)

## Context

Phases 1–2 left a working pipeline and a session-authed skeleton whose dashboard
renders only radar names. This phase builds the real product surface: a filterable
paper feed with AI-summary cards, inline paper detail with user actions, radar
management pages, and the Paper API capabilities those need (enriched list
serializer, filter params, full-text search).

Decisions made during brainstorming:

- **Layout:** sidebar filters + feed with inline card expansion (chosen from
  mockups; no master–detail pane, no top filter bar).
- **Radar management:** separate `/radars/` pages with classic Django forms
  (consistent with the auth pages); the only JS is the "Fetch now" button.
- **Pagination:** "Load more" button using DRF's `next` URL (page size 20).
- **Search:** Postgres full-text search, computed on the fly (no stored vector
  column or GIN index yet — acceptable to tens of thousands of rows; an index can
  be added later without API changes).
- **JS architecture:** small ES modules + `<template>` elements cloned by JS
  (no framework, no build step). Markup lives in Django templates; JS is logic-only.

## Part 1 — Paper API changes

### List serializer enrichment

`GET /api/papers/` gains two nested read-only objects per paper:

- `aisummary` (slim card shape): `one_line_summary`, `relevance_score`,
  `novelty_tag`, `dataset_used`, `model_architecture`, `sample_size`,
  `reported_metrics`. `null` when the paper has no summary. `key_findings_json`
  remains detail-only.
- `user_action`: `is_bookmarked`, `is_read`, `is_dismissed`, `custom_tags_json`
  for the requesting user; `null` if the user has never acted on the paper.

Query hygiene: `select_related("aisummary")` plus a filtered `Prefetch` of the
requesting user's `UserPaperAction` rows — constant query count per page,
locked in by a query-count test.

### Filters

Filtering logic moves from the view into `apps/papers/filters.py` —
`filter_papers(qs, user, params)` — keeping the view thin and the matrix
unit-testable. Params:

| Param | Behavior |
| --- | --- |
| `radar` | papers found by that radar (existing) |
| `date_from` / `date_to` | `publication_date` range, ISO dates |
| `min_score` | `aisummary__relevance_score__gte` |
| `novelty` | exact `aisummary__novelty_tag` |
| `journal` | case-insensitive contains |
| `is_read` / `is_bookmarked` | per-user flags (existing) |
| `is_dismissed` | **dismissed papers are excluded by default**; only `is_dismissed=true` shows them |
| `search` | Postgres FTS (below) |

Invalid param values (bad date, non-numeric score, unknown novelty) are ignored,
not 400s — the filter UI stays resilient. Documented and tested.

### Search

`django.contrib.postgres` `SearchVector(title, abstract)` + `SearchQuery`,
computed on the fly. When `search` is present, ordering switches from
`-publication_date` to `SearchRank` descending.

## Part 2 — Radar management pages (`apps/web`)

- `/radars/` — list: name, truncated query, schedule, active status,
  `last_fetched_at`, Edit/Delete links, and a **Fetch now** button
  (`data-radar-id`); `static/js/radars.js` posts to `/api/radars/{id}/fetch/`
  via `apiFetch` and swaps the button label to "Queued ✓".
- `/radars/new/` and `/radars/{id}/edit/` — one `RadarForm` (`ModelForm`:
  `name`, `pubmed_query`, `schedule`, `is_active`). `filters_json` is
  deliberately not exposed in the UI (YAGNI; the API still supports it).
- `/radars/{id}/delete/` — confirm page, POST deletes.
- All views `LoginRequiredMixin`, user-scoped querysets (other users' radars
  404), redirect to `/radars/` on success.
- `base.html` navbar gains Dashboard and Radars links.

## Part 3 — Dashboard page + JS modules

### Template (`web/dashboard.html`)

Two-column layout:

- **Sidebar `<aside>`:** radar radio list (populated by JS from `/api/radars/`),
  min-score select, novelty select, date from/to inputs, journal text input,
  checkboxes (*unread only*, *bookmarked only*, *show dismissed*), search input
  (300 ms debounce).
- **Feed column:** card list, "Load more" button, loading/empty/error states.
- Two `<template>` elements — `#paper-card-template` and
  `#paper-detail-template` — cloned and filled by JS.

### Card and detail behavior

- Card shows: title, journal · publication date, relevance stars, novelty badge,
  methodology tag chips, one-line AI summary, bookmark icon; unsummarized papers
  render without the AI block. Read papers render dimmed.
- Click card → lazy `GET /api/papers/{id}/` → inline detail: full abstract,
  key-findings list, methodology table, PubMed link
  (`https://pubmed.ncbi.nlm.nih.gov/{pmid}/`), notes textarea + save,
  comma-separated tags input + save, bookmark/read/dismiss buttons.
- Actions `PATCH /api/papers/{id}/actions/`, optimistic update, revert + inline
  error on failure. **Dismiss removes the card from the feed immediately**
  (matches the API default exclusion). Read/unread is an explicit button —
  no auto-mark on expand.

### JS modules (all ES modules importing `js/api.js`)

| Module | Responsibility |
| --- | --- |
| `filters.js` | sidebar state → query string; dispatches `filters-changed` (debounced search) |
| `feed.js` | listens for `filters-changed`; fetches `/api/papers/`; clones cards; owns Load more + loading/empty/error states |
| `paper.js` | card expansion (lazy detail fetch + template fill); action buttons; notes/tags saving |
| `dashboard.js` | entry point wiring the modules |
| `radars.js` | Fetch-now button on the radar list page |

### api.js enrichment

Thrown errors gain `err.status` and `err.body` (parsed JSON when available) —
the Phase 2 deferred item, needed now that mutating callers exist. `paper.js`
distinguishes 403 (session expired → "Please log in again" link) from
validation errors.

## Error handling summary

- Feed load failure → message with retry link.
- Action PATCH failure → revert optimistic update, small inline error.
- Invalid filter inputs → ignored server-side (defensive parsing), so the UI
  cannot wedge itself.

## Testing

- **API:** `apps/papers/tests/test_filters.py` (every param, combinations,
  dismissed-by-default, invalid-param tolerance, FTS match + rank ordering) and
  extended `test_papers.py` (serializer enrichment shape for both `aisummary`
  and `user_action` incl. nulls; query-count guard).
- **Web:** `apps/web/tests/test_radar_pages.py` — CRUD flows, user-scoping
  404s, form validation errors.
- **Dashboard template test:** page renders with both `<template>` elements and
  the sidebar controls — locks the JS↔template contract.
- JS remains framework-untested (no JS runner, consistent with Phase 2); its
  API contract is pinned by the backend tests. Final verification: full suite,
  ruff, curl smoke test, and a manual browser pass (filter, expand, bookmark,
  dismiss).

## Out of scope (Phase 4)

- Exports (BibTeX/RIS/CSV), weekly digest, trend analytics.
- Stored search-vector column + GIN index (add when corpus growth demands it).
- `filters_json` radar UI (journal whitelist/article types at fetch time).
