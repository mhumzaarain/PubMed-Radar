# Dashboard UI + Paper API Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the real dashboard — filterable AI-summary paper feed with inline detail and user actions, radar management pages — plus the Paper API filters/search/serializer enrichment it needs.

**Architecture:** Backend first: enrich the paper list serializer (`aisummary` card shape + per-user `user_action`), move filtering into a testable `apps/papers/filters.py` (with dismissed-by-default exclusion and graceful invalid-param handling), add on-the-fly Postgres FTS. Then Django-form radar pages, then the dashboard template (sidebar + `<template>` elements) and four ES modules (`filters.js`, `feed.js`, `paper.js`, entry `dashboard.js`) built on the existing `api.js` seam.

**Tech Stack:** Django 5.1, DRF (SessionAuthentication), django.contrib.postgres search, vanilla ES modules (no build step), pytest.

**Spec:** `docs/superpowers/specs/2026-06-12-dashboard-ui-design.md`
**Branch:** `dashboard-ui`. Do NOT commit to `main`.

**Conventions:**

- All commands run from `/workspace/backend` with `uv run`.
- Baseline: 110 tests passing, ruff clean (line-length 100, rules E/F/I).
- Commit steps assume normal per-task commits; if the user has requested
  stage-only execution (as in Phase 2), skip every commit step and leave
  changes in the working tree.
- Environment note: occasionally a single test times out on slow DB setup —
  re-run it in isolation before concluding breakage.
- JS has no test runner; its API contract is pinned by backend tests, its
  template contract by the dashboard template test (Task 5), and behavior by
  the Task 8 smoke pass.

---

### Task 1: Paper serializer enrichment (aisummary card + user_action)

**Files:**
- Modify: `backend/apps/papers/serializers.py`
- Modify: `backend/apps/papers/views.py`
- Test: `backend/apps/papers/tests/test_papers.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/papers/tests/test_papers.py`:

```python
@pytest.mark.django_db
class TestPaperListEnrichment:
    def test_list_includes_aisummary_card_fields(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        AISummaryFactory(
            paper=pr.paper,
            one_line_summary="One-liner.",
            relevance_score=4,
            novelty_tag="benchmark",
            dataset_used="LIDC",
        )
        response = client.get(PAPERS_URL)
        summary = response.data["results"][0]["aisummary"]
        assert summary["one_line_summary"] == "One-liner."
        assert summary["relevance_score"] == 4
        assert summary["novelty_tag"] == "benchmark"
        assert summary["dataset_used"] == "LIDC"
        assert "key_findings_json" not in summary

    def test_list_aisummary_null_when_unsummarized(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        PaperRadarFactory(radar=radar)
        response = client.get(PAPERS_URL)
        assert response.data["results"][0]["aisummary"] is None

    def test_list_includes_user_action(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        UserPaperActionFactory(
            user=user, paper=pr.paper, is_bookmarked=True, custom_tags_json=["thesis"]
        )
        response = client.get(PAPERS_URL)
        action = response.data["results"][0]["user_action"]
        assert action["is_bookmarked"] is True
        assert action["is_read"] is False
        assert action["custom_tags_json"] == ["thesis"]

    def test_list_user_action_null_when_untouched(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        PaperRadarFactory(radar=radar)
        response = client.get(PAPERS_URL)
        assert response.data["results"][0]["user_action"] is None

    def test_list_user_action_is_own_not_other_users(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        UserPaperActionFactory(user=UserFactory(), paper=pr.paper, is_bookmarked=True)
        response = client.get(PAPERS_URL)
        assert response.data["results"][0]["user_action"] is None

    def test_list_query_count_is_constant(self, auth_client, django_assert_max_num_queries):
        client, user = auth_client
        radar = RadarFactory(user=user)
        for _ in range(5):
            pr = PaperRadarFactory(radar=radar)
            AISummaryFactory(paper=pr.paper)
            UserPaperActionFactory(user=user, paper=pr.paper)
        with django_assert_max_num_queries(6):
            response = client.get(PAPERS_URL)
        assert len(response.data["results"]) == 5


@pytest.mark.django_db
class TestPaperDetailUserAction:
    def test_detail_includes_user_action(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        UserPaperActionFactory(user=user, paper=pr.paper, notes_text="my note")
        response = client.get(f"{PAPERS_URL}{pr.paper.id}/")
        assert response.data["user_action"]["notes_text"] == "my note"

    def test_detail_user_action_null_when_untouched(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        response = client.get(f"{PAPERS_URL}{pr.paper.id}/")
        assert response.data["user_action"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /workspace/backend && uv run pytest apps/papers/tests/test_papers.py -v -k "Enrichment or DetailUserAction"`
Expected: 8 FAIL (KeyError `aisummary` / `user_action` on the list shape; detail missing `user_action`).

- [ ] **Step 3: Implement serializers**

In `backend/apps/papers/serializers.py`, add after `AISummarySerializer`:

```python
class AISummaryCardSerializer(serializers.ModelSerializer):
    """Slim shape for feed cards; key_findings_json stays detail-only."""

    class Meta:
        model = AISummary
        fields = (
            "one_line_summary",
            "relevance_score",
            "novelty_tag",
            "dataset_used",
            "model_architecture",
            "sample_size",
            "reported_metrics",
        )
        read_only_fields = fields


class UserActionMixin(serializers.Serializer):
    user_action = serializers.SerializerMethodField()

    def get_user_action(self, obj):
        # Populated by the view's Prefetch(..., to_attr="my_actions").
        actions = getattr(obj, "my_actions", [])
        if not actions:
            return None
        action = actions[0]
        return {
            "is_bookmarked": action.is_bookmarked,
            "is_read": action.is_read,
            "is_dismissed": action.is_dismissed,
            "custom_tags_json": action.custom_tags_json,
            "notes_text": action.notes_text,
        }
```

Change `PaperListSerializer` to:

```python
class PaperListSerializer(UserActionMixin, serializers.ModelSerializer):
    aisummary = AISummaryCardSerializer(read_only=True, allow_null=True, default=None)

    class Meta:
        model = Paper
        fields = (
            "id",
            "pmid",
            "title",
            "authors_json",
            "journal",
            "doi",
            "publication_date",
            "article_type",
            "created_at",
            "aisummary",
            "user_action",
        )
        read_only_fields = fields

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if not hasattr(instance, "aisummary"):
            rep["aisummary"] = None
        return rep
```

Change `PaperDetailSerializer` to inherit the mixin and include the field —
class line becomes `class PaperDetailSerializer(UserActionMixin, serializers.ModelSerializer):`
and `"user_action",` is appended to its `fields` tuple. Its existing
`to_representation` stays as is.

- [ ] **Step 4: Wire the queryset in the view**

In `backend/apps/papers/views.py`, add imports and replace the base queryset
(keep the existing filter params for now — Task 2 replaces them):

```python
from django.db.models import Prefetch
```

and in `get_queryset`, change the first statement to:

```python
        qs = (
            Paper.objects.filter(paper_radars__radar__user=self.request.user)
            .distinct()
            .select_related("aisummary")
            .prefetch_related(
                Prefetch(
                    "user_actions",
                    queryset=UserPaperAction.objects.filter(user=self.request.user),
                    to_attr="my_actions",
                )
            )
        )
```

Also add the same `select_related`/`prefetch_related` for the detail route —
since `get_queryset` is shared by list and retrieve, this single change covers
both.

- [ ] **Step 5: Run tests**

Run: `cd /workspace/backend && uv run pytest apps/papers/ -v`
Expected: all pass (8 new + existing).

- [ ] **Step 6: Lint, full suite, commit**

```bash
cd /workspace/backend && uv run ruff check . && uv run pytest -q
cd /workspace && git add backend/apps/papers/
git commit -m "feat: enrich paper API with aisummary card and user_action

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 118 passed.

---

### Task 2: Filter module (apps/papers/filters.py)

**Files:**
- Create: `backend/apps/papers/filters.py`
- Modify: `backend/apps/papers/views.py`
- Test: `backend/apps/papers/tests/test_filters.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/apps/papers/tests/test_filters.py`:

```python
from datetime import date

import pytest

from apps.papers.factories import (
    AISummaryFactory,
    PaperFactory,
    PaperRadarFactory,
    UserPaperActionFactory,
)
from apps.radars.factories import RadarFactory

PAPERS_URL = "/api/papers/"


def _paper_for(user, **paper_kwargs):
    radar = RadarFactory(user=user)
    paper = PaperFactory(**paper_kwargs)
    PaperRadarFactory(paper=paper, radar=radar)
    return paper


def _pmids(response):
    return {row["pmid"] for row in response.data["results"]}


@pytest.mark.django_db
class TestDateFilters:
    def test_date_range(self, auth_client):
        client, user = auth_client
        old = _paper_for(user, publication_date=date(2024, 1, 1))
        mid = _paper_for(user, publication_date=date(2025, 6, 1))
        new = _paper_for(user, publication_date=date(2026, 6, 1))
        response = client.get(
            PAPERS_URL, {"date_from": "2025-01-01", "date_to": "2025-12-31"}
        )
        assert _pmids(response) == {mid.pmid}
        assert old.pmid not in _pmids(response)
        assert new.pmid not in _pmids(response)

    def test_invalid_date_ignored(self, auth_client):
        client, user = auth_client
        _paper_for(user)
        response = client.get(PAPERS_URL, {"date_from": "not-a-date"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1


@pytest.mark.django_db
class TestScoreAndNoveltyFilters:
    def test_min_score(self, auth_client):
        client, user = auth_client
        high = _paper_for(user)
        AISummaryFactory(paper=high, relevance_score=4)
        low = _paper_for(user)
        AISummaryFactory(paper=low, relevance_score=2)
        _paper_for(user)  # unsummarized — excluded by the join
        response = client.get(PAPERS_URL, {"min_score": "3"})
        assert _pmids(response) == {high.pmid}

    def test_invalid_min_score_ignored(self, auth_client):
        client, user = auth_client
        _paper_for(user)
        response = client.get(PAPERS_URL, {"min_score": "high"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_novelty(self, auth_client):
        client, user = auth_client
        rev = _paper_for(user)
        AISummaryFactory(paper=rev, novelty_tag="review")
        inc = _paper_for(user)
        AISummaryFactory(paper=inc, novelty_tag="incremental")
        response = client.get(PAPERS_URL, {"novelty": "review"})
        assert _pmids(response) == {rev.pmid}

    def test_unknown_novelty_ignored(self, auth_client):
        client, user = auth_client
        paper = _paper_for(user)
        AISummaryFactory(paper=paper, novelty_tag="review")
        response = client.get(PAPERS_URL, {"novelty": "groundbreaking"})
        assert len(response.data["results"]) == 1


@pytest.mark.django_db
class TestJournalAndRadarFilters:
    def test_journal_icontains(self, auth_client):
        client, user = auth_client
        match = _paper_for(user, journal="Radiology Today")
        _paper_for(user, journal="JAMA")
        response = client.get(PAPERS_URL, {"journal": "radiology"})
        assert _pmids(response) == {match.pmid}

    def test_invalid_radar_uuid_ignored(self, auth_client):
        client, user = auth_client
        _paper_for(user)
        response = client.get(PAPERS_URL, {"radar": "not-a-uuid"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1


@pytest.mark.django_db
class TestFlagSemantics:
    def test_unread_includes_untouched_papers(self, auth_client):
        client, user = auth_client
        untouched = _paper_for(user)
        read = _paper_for(user)
        UserPaperActionFactory(user=user, paper=read, is_read=True)
        explicit_unread = _paper_for(user)
        UserPaperActionFactory(user=user, paper=explicit_unread, is_read=False)
        response = client.get(PAPERS_URL, {"is_read": "false"})
        assert _pmids(response) == {untouched.pmid, explicit_unread.pmid}

    def test_dismissed_excluded_by_default(self, auth_client):
        client, user = auth_client
        visible = _paper_for(user)
        dismissed = _paper_for(user)
        UserPaperActionFactory(user=user, paper=dismissed, is_dismissed=True)
        response = client.get(PAPERS_URL)
        assert _pmids(response) == {visible.pmid}

    def test_is_dismissed_true_shows_only_dismissed(self, auth_client):
        client, user = auth_client
        _paper_for(user)
        dismissed = _paper_for(user)
        UserPaperActionFactory(user=user, paper=dismissed, is_dismissed=True)
        response = client.get(PAPERS_URL, {"is_dismissed": "true"})
        assert _pmids(response) == {dismissed.pmid}

    def test_other_users_dismissal_does_not_hide_paper(self, auth_client):
        from apps.users.factories import UserFactory

        client, user = auth_client
        paper = _paper_for(user)
        UserPaperActionFactory(user=UserFactory(), paper=paper, is_dismissed=True)
        response = client.get(PAPERS_URL)
        assert _pmids(response) == {paper.pmid}


@pytest.mark.django_db
class TestCombinedFilters:
    def test_score_and_journal_combined(self, auth_client):
        client, user = auth_client
        match = _paper_for(user, journal="Radiology")
        AISummaryFactory(paper=match, relevance_score=5)
        wrong_journal = _paper_for(user, journal="JAMA")
        AISummaryFactory(paper=wrong_journal, relevance_score=5)
        low_score = _paper_for(user, journal="Radiology")
        AISummaryFactory(paper=low_score, relevance_score=1)
        response = client.get(PAPERS_URL, {"min_score": "4", "journal": "radiology"})
        assert _pmids(response) == {match.pmid}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /workspace/backend && uv run pytest apps/papers/tests/test_filters.py -v`
Expected: the date/score/novelty/journal/invalid-param and dismissed-default
tests FAIL (params not yet supported); `test_is_dismissed_true_shows_only_dismissed`
may pass with old semantics — fine.

- [ ] **Step 3: Implement the filter module**

Create `backend/apps/papers/filters.py`:

```python
import uuid
from datetime import date

from .models import AISummary

NOVELTY_TAGS = {key for key, _ in AISummary.NOVELTY_CHOICES}


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_uuid(value):
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value):
    if value is None:
        return None
    return value.lower() in ("true", "1")


def filter_papers(qs, user, params):
    """Apply feed filter params to a Paper queryset.

    Invalid values are ignored (never 400) so the filter UI cannot wedge
    itself. Flag semantics: papers with no UserPaperAction row count as
    unread/unbookmarked/undismissed. Dismissed papers are excluded unless
    is_dismissed=true is passed explicitly.
    """
    radar_id = _parse_uuid(params.get("radar"))
    if radar_id:
        qs = qs.filter(paper_radars__radar__id=radar_id)

    date_from = _parse_date(params.get("date_from"))
    if date_from:
        qs = qs.filter(publication_date__gte=date_from)
    date_to = _parse_date(params.get("date_to"))
    if date_to:
        qs = qs.filter(publication_date__lte=date_to)

    min_score = _parse_int(params.get("min_score"))
    if min_score is not None:
        qs = qs.filter(aisummary__relevance_score__gte=min_score)

    novelty = params.get("novelty")
    if novelty in NOVELTY_TAGS:
        qs = qs.filter(aisummary__novelty_tag=novelty)

    journal = params.get("journal")
    if journal:
        qs = qs.filter(journal__icontains=journal)

    is_read = _parse_bool(params.get("is_read"))
    if is_read is True:
        qs = qs.filter(user_actions__user=user, user_actions__is_read=True)
    elif is_read is False:
        qs = qs.exclude(user_actions__user=user, user_actions__is_read=True)

    is_bookmarked = _parse_bool(params.get("is_bookmarked"))
    if is_bookmarked is True:
        qs = qs.filter(user_actions__user=user, user_actions__is_bookmarked=True)
    elif is_bookmarked is False:
        qs = qs.exclude(user_actions__user=user, user_actions__is_bookmarked=True)

    if _parse_bool(params.get("is_dismissed")) is True:
        qs = qs.filter(user_actions__user=user, user_actions__is_dismissed=True)
    else:
        qs = qs.exclude(user_actions__user=user, user_actions__is_dismissed=True)

    return qs.order_by("-publication_date")
```

- [ ] **Step 4: Slim the view**

Replace `get_queryset` in `backend/apps/papers/views.py` with (and add
`from .filters import filter_papers` to the imports; the old inline
radar/flag filtering and `order_by` go away):

```python
    def get_queryset(self):
        qs = (
            Paper.objects.filter(paper_radars__radar__user=self.request.user)
            .distinct()
            .select_related("aisummary")
            .prefetch_related(
                Prefetch(
                    "user_actions",
                    queryset=UserPaperAction.objects.filter(user=self.request.user),
                    to_attr="my_actions",
                )
            )
        )
        return filter_papers(qs, self.request.user, self.request.query_params)
```

- [ ] **Step 5: Run tests**

Run: `cd /workspace/backend && uv run pytest apps/papers/ -v`
Expected: all pass, including the pre-existing `TestPaperList` filter tests
(their `is_read=true`/`is_bookmarked=true`/`is_dismissed=true` semantics are
unchanged).

- [ ] **Step 6: Lint, full suite, commit**

```bash
cd /workspace/backend && uv run ruff check . && uv run pytest -q
cd /workspace && git add backend/apps/papers/
git commit -m "feat: add paper feed filters with dismissed-by-default exclusion

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 131 passed.

---

### Task 3: Full-text search

**Files:**
- Modify: `backend/config/settings.py` (add django.contrib.postgres)
- Modify: `backend/apps/papers/filters.py`
- Test: `backend/apps/papers/tests/test_filters.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/papers/tests/test_filters.py`:

```python
@pytest.mark.django_db
class TestSearch:
    def test_search_matches_title_and_abstract(self, auth_client):
        client, user = auth_client
        in_title = _paper_for(user, title="Pneumonia detection with CNNs", abstract="x")
        in_abstract = _paper_for(
            user, title="Imaging study", abstract="We evaluate pneumonia outcomes."
        )
        _paper_for(user, title="Cardiac MRI segmentation", abstract="Hearts only.")
        response = client.get(PAPERS_URL, {"search": "pneumonia"})
        assert _pmids(response) == {in_title.pmid, in_abstract.pmid}

    def test_search_uses_stemming(self, auth_client):
        client, user = auth_client
        paper = _paper_for(user, title="Detecting nodules", abstract="x")
        response = client.get(PAPERS_URL, {"search": "detection"})
        assert _pmids(response) == {paper.pmid}

    def test_search_orders_by_rank(self, auth_client):
        client, user = auth_client
        twice = _paper_for(
            user, title="Sepsis prediction models", abstract="Sepsis onset predicted early."
        )
        once = _paper_for(user, title="ICU outcomes", abstract="Includes sepsis cohort.")
        response = client.get(PAPERS_URL, {"search": "sepsis"})
        pmids = [row["pmid"] for row in response.data["results"]]
        assert pmids == [twice.pmid, once.pmid]

    def test_blank_search_ignored(self, auth_client):
        client, user = auth_client
        _paper_for(user)
        response = client.get(PAPERS_URL, {"search": "   "})
        assert len(response.data["results"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /workspace/backend && uv run pytest apps/papers/tests/test_filters.py::TestSearch -v`
Expected: the first three FAIL (search param currently ignored, so all papers
return); `test_blank_search_ignored` passes.

- [ ] **Step 3: Implement**

In `backend/config/settings.py`, add `"django.contrib.postgres",` to
`DJANGO_APPS` (after staticfiles).

In `backend/apps/papers/filters.py`, add the import:

```python
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
```

and replace the final `return qs.order_by("-publication_date")` with:

```python
    search = (params.get("search") or "").strip()
    if search:
        vector = SearchVector("title", "abstract")
        query = SearchQuery(search)
        return (
            qs.annotate(fts=vector, rank=SearchRank(vector, query))
            .filter(fts=query)
            .order_by("-rank", "-publication_date")
        )

    return qs.order_by("-publication_date")
```

- [ ] **Step 4: Run tests**

Run: `cd /workspace/backend && uv run pytest apps/papers/ -v`
Expected: all pass.

- [ ] **Step 5: Lint, full suite, commit**

```bash
cd /workspace/backend && uv run ruff check . && uv run pytest -q
cd /workspace && git add backend/apps/papers/ backend/config/settings.py
git commit -m "feat: add Postgres full-text search to paper feed

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 135 passed.

---

### Task 4: Radar management pages

**Files:**
- Modify: `backend/apps/web/forms.py`, `backend/apps/web/views.py`, `backend/apps/web/urls.py`
- Create: `backend/templates/web/radar_list.html`, `backend/templates/web/radar_form.html`, `backend/templates/web/radar_confirm_delete.html`
- Create: `backend/static/js/radars.js`
- Modify: `backend/templates/base.html` (navbar links)
- Test: `backend/apps/web/tests/test_radar_pages.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/apps/web/tests/test_radar_pages.py`:

```python
import pytest

from apps.radars.factories import RadarFactory
from apps.radars.models import Radar
from apps.users.factories import UserFactory

RADARS_PAGE = "/radars/"


@pytest.mark.django_db
class TestRadarListPage:
    def test_requires_login(self, client):
        response = client.get(RADARS_PAGE)
        assert response.status_code == 302
        assert response.url.startswith("/login/")

    def test_lists_only_own_radars(self, client):
        user = UserFactory()
        mine = RadarFactory(user=user, name="My lung radar")
        RadarFactory(user=UserFactory(), name="Someone elses")
        client.force_login(user)
        response = client.get(RADARS_PAGE)
        assert response.status_code == 200
        assert b"My lung radar" in response.content
        assert b"Someone elses" not in response.content

    def test_has_fetch_now_button(self, client):
        user = UserFactory()
        radar = RadarFactory(user=user)
        client.force_login(user)
        response = client.get(RADARS_PAGE)
        assert f'data-radar-fetch="{radar.id}"'.encode() in response.content


@pytest.mark.django_db
class TestRadarCreate:
    def test_create_sets_user_and_redirects(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.post(
            f"{RADARS_PAGE}new/",
            {"name": "CT radar", "pubmed_query": "lung AND CT", "schedule": "daily"},
        )
        assert response.status_code == 302
        assert response.url == RADARS_PAGE
        radar = Radar.objects.get(name="CT radar")
        assert radar.user == user
        assert radar.is_active is True

    def test_invalid_form_rerenders_with_errors(self, client):
        client.force_login(UserFactory())
        response = client.post(
            f"{RADARS_PAGE}new/", {"name": "", "pubmed_query": "x", "schedule": "daily"}
        )
        assert response.status_code == 200
        assert response.context["form"].errors


@pytest.mark.django_db
class TestRadarUpdateDelete:
    def test_edit_own_radar(self, client):
        user = UserFactory()
        radar = RadarFactory(user=user, name="Old name")
        client.force_login(user)
        response = client.post(
            f"{RADARS_PAGE}{radar.id}/edit/",
            {
                "name": "New name",
                "pubmed_query": radar.pubmed_query,
                "schedule": radar.schedule,
                "is_active": "on",
            },
        )
        assert response.status_code == 302
        radar.refresh_from_db()
        assert radar.name == "New name"

    def test_edit_other_users_radar_404(self, client):
        radar = RadarFactory(user=UserFactory())
        client.force_login(UserFactory())
        response = client.get(f"{RADARS_PAGE}{radar.id}/edit/")
        assert response.status_code == 404

    def test_delete_own_radar(self, client):
        user = UserFactory()
        radar = RadarFactory(user=user)
        client.force_login(user)
        response = client.post(f"{RADARS_PAGE}{radar.id}/delete/")
        assert response.status_code == 302
        assert not Radar.objects.filter(id=radar.id).exists()

    def test_delete_other_users_radar_404(self, client):
        radar = RadarFactory(user=UserFactory())
        client.force_login(UserFactory())
        response = client.post(f"{RADARS_PAGE}{radar.id}/delete/")
        assert response.status_code == 404
        assert Radar.objects.filter(id=radar.id).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /workspace/backend && uv run pytest apps/web/tests/test_radar_pages.py -v`
Expected: all FAIL with 404s (no routes).

- [ ] **Step 3: Implement form and views**

Append to `backend/apps/web/forms.py` (add `from apps.radars.models import Radar`
to imports):

```python
class RadarForm(forms.ModelForm):
    class Meta:
        model = Radar
        fields = ("name", "pubmed_query", "schedule", "is_active")
        widgets = {"pubmed_query": forms.Textarea(attrs={"rows": 3})}
```

Append to `backend/apps/web/views.py` (extend imports accordingly):

```python
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.radars.models import Radar

from .forms import RadarForm, RegisterForm
```

```python
class RadarQuerysetMixin(LoginRequiredMixin):
    model = Radar

    def get_queryset(self):
        return Radar.objects.filter(user=self.request.user)


class RadarListView(RadarQuerysetMixin, ListView):
    template_name = "web/radar_list.html"
    context_object_name = "radars"


class RadarCreateView(LoginRequiredMixin, CreateView):
    model = Radar
    form_class = RadarForm
    template_name = "web/radar_form.html"
    success_url = reverse_lazy("radar-list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class RadarUpdateView(RadarQuerysetMixin, UpdateView):
    form_class = RadarForm
    template_name = "web/radar_form.html"
    success_url = reverse_lazy("radar-list")


class RadarDeleteView(RadarQuerysetMixin, DeleteView):
    template_name = "web/radar_confirm_delete.html"
    success_url = reverse_lazy("radar-list")
```

Add to `urlpatterns` in `backend/apps/web/urls.py`:

```python
    path("radars/", views.RadarListView.as_view(), name="radar-list"),
    path("radars/new/", views.RadarCreateView.as_view(), name="radar-create"),
    path("radars/<uuid:pk>/edit/", views.RadarUpdateView.as_view(), name="radar-edit"),
    path("radars/<uuid:pk>/delete/", views.RadarDeleteView.as_view(), name="radar-delete"),
```

- [ ] **Step 4: Templates, JS, navbar**

`backend/templates/web/radar_list.html`:

```html
{% extends "base.html" %}
{% load static %}
{% block title %}Radars — PubMed Radar{% endblock %}
{% block content %}
<div class="page-header">
  <h1>Your radars</h1>
  <a class="button" href="{% url 'radar-create' %}">+ New radar</a>
</div>
{% if radars %}
<table class="radar-table">
  <thead>
    <tr><th>Name</th><th>Query</th><th>Schedule</th><th>Active</th><th>Last fetched</th><th></th></tr>
  </thead>
  <tbody>
    {% for radar in radars %}
    <tr>
      <td>{{ radar.name }}</td>
      <td class="query">{{ radar.pubmed_query|truncatechars:60 }}</td>
      <td>{{ radar.get_schedule_display }}</td>
      <td>{{ radar.is_active|yesno:"Yes,No" }}</td>
      <td>{{ radar.last_fetched_at|date:"Y-m-d H:i"|default:"never" }}</td>
      <td class="row-actions">
        <button type="button" data-radar-fetch="{{ radar.id }}">Fetch now</button>
        <a href="{% url 'radar-edit' radar.id %}">Edit</a>
        <a href="{% url 'radar-delete' radar.id %}">Delete</a>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% else %}
<p>No radars yet — create one to start monitoring PubMed.</p>
{% endif %}
{% endblock %}
{% block scripts %}
<script type="module" src="{% static 'js/radars.js' %}"></script>
{% endblock %}
```

`backend/templates/web/radar_form.html`:

```html
{% extends "base.html" %}
{% block title %}{% if form.instance.pk %}Edit{% else %}New{% endif %} radar — PubMed Radar{% endblock %}
{% block content %}
<h1>{% if form.instance.pk %}Edit radar{% else %}New radar{% endif %}</h1>
<form method="post" class="auth-form">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">Save</button>
  <a href="{% url 'radar-list' %}">Cancel</a>
</form>
{% endblock %}
```

`backend/templates/web/radar_confirm_delete.html`:

```html
{% extends "base.html" %}
{% block title %}Delete radar — PubMed Radar{% endblock %}
{% block content %}
<h1>Delete radar</h1>
<p>Delete <strong>{{ object.name }}</strong>? Papers it found stay in your feed.</p>
<form method="post">
  {% csrf_token %}
  <button type="submit">Yes, delete</button>
  <a href="{% url 'radar-list' %}">Cancel</a>
</form>
{% endblock %}
```

`backend/static/js/radars.js`:

```javascript
import { apiFetch } from "./api.js";

document.querySelectorAll("[data-radar-fetch]").forEach((button) => {
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await apiFetch(`/api/radars/${button.dataset.radarFetch}/fetch/`, {
        method: "POST",
      });
      button.textContent = "Queued ✓";
    } catch (err) {
      console.error(err);
      button.textContent = "Failed — retry";
      button.disabled = false;
    }
  });
});
```

In `backend/templates/base.html`, inside the `{% if user.is_authenticated %}`
block, add nav links before the `.nav-user` div:

```html
      <div class="nav-links">
        <a href="{% url 'dashboard' %}">Dashboard</a>
        <a href="{% url 'radar-list' %}">Radars</a>
      </div>
```

- [ ] **Step 5: Run tests**

Run: `cd /workspace/backend && uv run pytest apps/web/ -v`
Expected: all pass (21 existing + 9 new).

- [ ] **Step 6: Lint, full suite, commit**

```bash
cd /workspace/backend && uv run ruff check . && uv run pytest -q
cd /workspace && git add backend/apps/web/ backend/templates/ backend/static/js/radars.js
git commit -m "feat: add radar management pages with fetch-now button

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 144 passed.

---

### Task 5: Dashboard template + CSS + contract test

**Files:**
- Modify: `backend/templates/web/dashboard.html` (full rewrite)
- Modify: `backend/static/css/app.css` (append)
- Test: `backend/apps/web/tests/test_dashboard_template.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/apps/web/tests/test_dashboard_template.py`:

```python
import pytest

from apps.users.factories import UserFactory

REQUIRED_IDS = [
    'id="filter-radars"',
    'id="filter-min-score"',
    'id="filter-novelty"',
    'id="filter-date-from"',
    'id="filter-date-to"',
    'id="filter-journal"',
    'id="filter-unread"',
    'id="filter-bookmarked"',
    'id="filter-dismissed"',
    'id="search-input"',
    'id="feed"',
    'id="feed-status"',
    'id="load-more"',
    'id="paper-card-template"',
    'id="paper-detail-template"',
]


@pytest.mark.django_db
class TestDashboardTemplateContract:
    def test_dashboard_contains_js_contract_elements(self, client):
        client.force_login(UserFactory())
        response = client.get("/")
        assert response.status_code == 200
        content = response.content.decode()
        for required in REQUIRED_IDS:
            assert required in content, f"missing {required}"

    def test_dashboard_loads_module_entrypoint(self, client):
        client.force_login(UserFactory())
        response = client.get("/")
        assert b'js/dashboard.js' in response.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /workspace/backend && uv run pytest apps/web/tests/test_dashboard_template.py -v`
Expected: first test FAILS (sidebar ids missing); second passes.

- [ ] **Step 3: Rewrite the dashboard template**

Replace `backend/templates/web/dashboard.html` entirely with:

```html
{% extends "base.html" %}
{% load static %}
{% block title %}Dashboard — PubMed Radar{% endblock %}
{% block content %}
<div class="dashboard">
  <aside class="sidebar">
    <section>
      <h3>Radars</h3>
      <ul id="filter-radars" class="radar-filter-list">
        <li><label><input type="radio" name="radar" value="" checked> All radars</label></li>
      </ul>
    </section>
    <section>
      <h3>Filters</h3>
      <label>Min relevance
        <select id="filter-min-score">
          <option value="">Any</option>
          <option value="2">2+</option>
          <option value="3">3+</option>
          <option value="4">4+</option>
          <option value="5">5</option>
        </select>
      </label>
      <label>Novelty
        <select id="filter-novelty">
          <option value="">Any</option>
          <option value="incremental">Incremental</option>
          <option value="new_approach">New approach</option>
          <option value="review">Review</option>
          <option value="benchmark">Benchmark</option>
          <option value="dataset">Dataset</option>
          <option value="meta_analysis">Meta-analysis</option>
        </select>
      </label>
      <label>From <input type="date" id="filter-date-from"></label>
      <label>To <input type="date" id="filter-date-to"></label>
      <label>Journal <input type="text" id="filter-journal" placeholder="e.g. Radiology"></label>
      <label class="check"><input type="checkbox" id="filter-unread"> Unread only</label>
      <label class="check"><input type="checkbox" id="filter-bookmarked"> Bookmarked only</label>
      <label class="check"><input type="checkbox" id="filter-dismissed"> Show dismissed</label>
    </section>
    <section>
      <h3>Search</h3>
      <input type="search" id="search-input" placeholder="Title or abstract…">
    </section>
  </aside>

  <section class="feed-column">
    <h1>Your papers</h1>
    <div id="feed-status" hidden></div>
    <div id="feed"></div>
    <button id="load-more" type="button" hidden>Load more</button>
  </section>
</div>

<template id="paper-card-template">
  <article class="paper-card">
    <header class="paper-card-header">
      <h3 data-field="title"></h3>
      <span class="bookmark-indicator" data-field="bookmark" hidden>🔖</span>
    </header>
    <p class="paper-meta">
      <span data-field="journal"></span> · <span data-field="date"></span>
      <span class="score" data-field="score"></span>
      <span class="badge" data-field="novelty" hidden></span>
    </p>
    <p class="summary" data-field="summary" hidden></p>
    <p class="method-tags" data-field="method-tags"></p>
    <div class="paper-detail" hidden></div>
  </article>
</template>

<template id="paper-detail-template">
  <div class="detail-body">
    <h4>Abstract</h4>
    <p data-field="abstract"></p>
    <h4>Key findings</h4>
    <ul data-field="findings"></ul>
    <h4>Methodology</h4>
    <table class="methodology">
      <tr><th>Dataset</th><td data-field="dataset"></td></tr>
      <tr><th>Architecture</th><td data-field="architecture"></td></tr>
      <tr><th>Sample size</th><td data-field="sample-size"></td></tr>
      <tr><th>Metrics</th><td data-field="metrics"></td></tr>
    </table>
    <p><a data-field="pubmed-link" target="_blank" rel="noopener">View on PubMed →</a></p>
    <div class="detail-actions">
      <button type="button" data-action="bookmark">Bookmark</button>
      <button type="button" data-action="read">Read / unread</button>
      <button type="button" data-action="dismiss">Dismiss</button>
    </div>
    <label>Tags (comma-separated)
      <input type="text" data-field="tags-input">
    </label>
    <button type="button" data-action="save-tags">Save tags</button>
    <label>Notes
      <textarea data-field="notes-input" rows="3"></textarea>
    </label>
    <button type="button" data-action="save-notes">Save notes</button>
    <p class="action-error" data-field="action-error" hidden></p>
  </div>
</template>
{% endblock %}
{% block scripts %}
<script type="module" src="{% static 'js/dashboard.js' %}"></script>
{% endblock %}
```

- [ ] **Step 4: Append dashboard CSS**

Append to `backend/static/css/app.css`:

```css
.nav-links { display: flex; gap: 1rem; }
.nav-links a { color: #cfe3f5; text-decoration: none; }
.dashboard { display: flex; gap: 1.5rem; align-items: flex-start; }
.sidebar {
  flex: 0 0 220px; background: #f5f7fa; border-radius: 8px; padding: 1rem;
  font-size: 0.9rem;
}
.sidebar h3 { margin: 0.5rem 0 0.25rem; font-size: 0.85rem; text-transform: uppercase; }
.sidebar label { display: block; margin-top: 0.5rem; }
.sidebar label.check { margin-top: 0.35rem; }
.sidebar input[type="text"], .sidebar input[type="date"],
.sidebar input[type="search"], .sidebar select { width: 100%; padding: 0.3rem; }
.radar-filter-list { list-style: none; margin: 0; padding: 0; }
.feed-column { flex: 1; min-width: 0; }
.paper-card {
  border: 1px solid #d8dee6; border-radius: 8px; padding: 0.75rem 1rem;
  margin-bottom: 0.75rem; cursor: pointer;
}
.paper-card.is-read { opacity: 0.6; }
.paper-card-header { display: flex; justify-content: space-between; gap: 0.5rem; }
.paper-card-header h3 { margin: 0; font-size: 1.05rem; }
.paper-meta { color: #555; font-size: 0.85rem; margin: 0.25rem 0; }
.score { color: #c98a00; letter-spacing: 1px; }
.badge {
  background: #e3edf7; color: #16324f; border-radius: 10px;
  padding: 0.05rem 0.5rem; font-size: 0.75rem;
}
.summary { margin: 0.25rem 0; }
.method-tags { color: #666; font-size: 0.8rem; margin: 0.25rem 0 0; }
.paper-detail { border-top: 1px solid #e2e8f0; margin-top: 0.75rem; padding-top: 0.75rem; cursor: auto; }
.paper-detail h4 { margin: 0.75rem 0 0.25rem; }
.methodology th { text-align: left; padding-right: 1rem; color: #555; font-weight: 600; }
.detail-actions { display: flex; gap: 0.5rem; margin: 0.75rem 0; }
.action-error { color: #b00020; font-size: 0.85rem; }
#feed-status { padding: 1rem 0; color: #555; }
#load-more { margin: 0.5rem 0 2rem; padding: 0.5rem 1.25rem; }
.page-header { display: flex; justify-content: space-between; align-items: center; }
.radar-table { width: 100%; border-collapse: collapse; }
.radar-table th, .radar-table td { text-align: left; padding: 0.5rem; border-bottom: 1px solid #e2e8f0; }
.row-actions { display: flex; gap: 0.5rem; align-items: center; }
```

- [ ] **Step 5: Update the stale Phase 2 assertion, then run tests**

The Phase 2 test `test_renders_for_logged_in_user` in
`backend/apps/web/tests/test_auth_pages.py` asserts `b'id="radar-list"'`,
an id that no longer exists in the rewritten template. Change that one
assertion to `assert b'id="feed"' in response.content` (keep the email
assertion).

Run: `cd /workspace/backend && uv run pytest apps/web/ -v`
Expected: all pass.

- [ ] **Step 6: Lint, full suite, commit**

```bash
cd /workspace/backend && uv run ruff check . && uv run pytest -q
cd /workspace && git add backend/templates/ backend/static/css/ backend/apps/web/tests/
git commit -m "feat: dashboard template with sidebar filters and card templates

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 146 passed.

---

### Task 6: JS — api.js errors, filters.js, feed.js, dashboard.js

**Files:**
- Modify: `backend/static/js/api.js`
- Create: `backend/static/js/filters.js`, `backend/static/js/feed.js`
- Modify: `backend/static/js/dashboard.js` (full rewrite)

No backend tests change in this task; verification is `findstatic`, the
template contract test, and the Task 8 browser smoke pass.

- [ ] **Step 1: Enrich api.js errors**

In `backend/static/js/api.js`, replace the `if (!response.ok) { ... }` block
with:

```javascript
  if (!response.ok) {
    const error = new Error(`API request failed: ${response.status} ${url}`);
    error.status = response.status;
    try {
      error.body = await response.json();
    } catch {
      error.body = null;
    }
    throw error;
  }
```

- [ ] **Step 2: Create `backend/static/js/filters.js`**

```javascript
import { apiFetch } from "./api.js";

let debounceTimer = null;

function emit() {
  document.dispatchEvent(new CustomEvent("filters-changed"));
}

export function currentQuery() {
  const params = new URLSearchParams();
  const radar = document.querySelector('#filter-radars input[name="radar"]:checked');
  if (radar && radar.value) params.set("radar", radar.value);
  const minScore = document.getElementById("filter-min-score").value;
  if (minScore) params.set("min_score", minScore);
  const novelty = document.getElementById("filter-novelty").value;
  if (novelty) params.set("novelty", novelty);
  const dateFrom = document.getElementById("filter-date-from").value;
  if (dateFrom) params.set("date_from", dateFrom);
  const dateTo = document.getElementById("filter-date-to").value;
  if (dateTo) params.set("date_to", dateTo);
  const journal = document.getElementById("filter-journal").value.trim();
  if (journal) params.set("journal", journal);
  if (document.getElementById("filter-unread").checked) params.set("is_read", "false");
  if (document.getElementById("filter-bookmarked").checked) {
    params.set("is_bookmarked", "true");
  }
  if (document.getElementById("filter-dismissed").checked) {
    params.set("is_dismissed", "true");
  }
  const search = document.getElementById("search-input").value.trim();
  if (search) params.set("search", search);
  return params.toString();
}

async function loadRadarList() {
  const list = document.getElementById("filter-radars");
  try {
    const data = await apiFetch("/api/radars/");
    for (const radar of data.results ?? data) {
      const li = document.createElement("li");
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "radar";
      input.value = radar.id;
      label.append(input, ` ${radar.name}`);
      li.appendChild(label);
      list.appendChild(li);
    }
  } catch (err) {
    console.error("Could not load radar list", err);
  }
}

export async function initFilters() {
  await loadRadarList();
  document.querySelector(".sidebar").addEventListener("change", emit);
  document.getElementById("search-input").addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(emit, 300);
  });
}
```

- [ ] **Step 3: Create `backend/static/js/feed.js`**

```javascript
import { apiFetch } from "./api.js";
import { currentQuery } from "./filters.js";

const NOVELTY_LABELS = {
  incremental: "Incremental",
  new_approach: "New approach",
  review: "Review",
  benchmark: "Benchmark",
  dataset: "Dataset",
  meta_analysis: "Meta-analysis",
};

let nextUrl = null;

function setStatus(text) {
  const status = document.getElementById("feed-status");
  status.hidden = !text;
  status.textContent = text || "";
}

function renderCard(paper) {
  const template = document.getElementById("paper-card-template");
  const card = template.content.firstElementChild.cloneNode(true);
  card.dataset.paperId = paper.id;
  card.dataset.pmid = paper.pmid;
  card.querySelector('[data-field="title"]').textContent = paper.title;
  card.querySelector('[data-field="journal"]').textContent = paper.journal;
  card.querySelector('[data-field="date"]').textContent = paper.publication_date;
  const summary = paper.aisummary;
  if (summary) {
    card.querySelector('[data-field="score"]').textContent =
      "★".repeat(summary.relevance_score);
    const badge = card.querySelector('[data-field="novelty"]');
    badge.textContent = NOVELTY_LABELS[summary.novelty_tag] ?? summary.novelty_tag;
    badge.hidden = false;
    const summaryEl = card.querySelector('[data-field="summary"]');
    summaryEl.textContent = summary.one_line_summary;
    summaryEl.hidden = false;
    const tags = [
      summary.dataset_used,
      summary.model_architecture,
      summary.sample_size,
      summary.reported_metrics,
    ].filter(Boolean);
    card.querySelector('[data-field="method-tags"]').textContent = tags.join(" · ");
  }
  const action = paper.user_action;
  if (action) {
    if (action.is_read) card.classList.add("is-read");
    card.querySelector('[data-field="bookmark"]').hidden = !action.is_bookmarked;
  }
  return card;
}

async function loadFeed({ reset }) {
  const feed = document.getElementById("feed");
  const loadMore = document.getElementById("load-more");
  if (reset) {
    feed.replaceChildren();
    nextUrl = null;
    setStatus("Loading…");
  }
  const url = reset ? `/api/papers/?${currentQuery()}` : nextUrl;
  try {
    const data = await apiFetch(url);
    setStatus("");
    for (const paper of data.results) feed.appendChild(renderCard(paper));
    nextUrl = data.next;
    loadMore.hidden = !nextUrl;
    if (reset && data.results.length === 0) {
      setStatus("No papers match the current filters.");
    }
  } catch (err) {
    console.error(err);
    setStatus("Could not load papers — try changing a filter or reloading.");
  }
}

export function initFeed() {
  document.addEventListener("filters-changed", () => loadFeed({ reset: true }));
  document
    .getElementById("load-more")
    .addEventListener("click", () => loadFeed({ reset: false }));
  loadFeed({ reset: true });
}
```

- [ ] **Step 4: Rewrite `backend/static/js/dashboard.js`**

```javascript
import { initFilters } from "./filters.js";
import { initFeed } from "./feed.js";
import { initPaperInteractions } from "./paper.js";

initFilters().then(() => {
  initFeed();
  initPaperInteractions();
});
```

(NOTE: `paper.js` is created in Task 7 — until then the dashboard page's module
import fails in the browser. Backend tests are unaffected; Task 7 follows
immediately. If executing tasks out of order, do Task 7 before manual browser
checks.)

- [ ] **Step 5: Verify static resolution + suite**

Run: `cd /workspace/backend && uv run python manage.py findstatic js/filters.js js/feed.js js/dashboard.js`
Expected: all found.

Run: `cd /workspace/backend && uv run pytest apps/web/ -q && uv run ruff check .`
Expected: all pass, clean.

- [ ] **Step 6: Commit**

```bash
cd /workspace && git add backend/static/js/
git commit -m "feat: add filters and feed JS modules with enriched api errors

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: JS — paper.js (expand, actions, notes/tags)

**Files:**
- Create: `backend/static/js/paper.js`

- [ ] **Step 1: Create `backend/static/js/paper.js`**

```javascript
import { apiFetch } from "./api.js";

function errorMessage(err) {
  if (err.status === 403) return "Session expired — please log in again.";
  return "Action failed — try again.";
}

function showError(card, message) {
  const el = card.querySelector('[data-field="action-error"]');
  if (el) {
    el.textContent = message;
    el.hidden = false;
  }
}

function patchAction(paperId, payload) {
  return apiFetch(`/api/papers/${paperId}/actions/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

function fillDetail(container, paper) {
  const template = document.getElementById("paper-detail-template");
  const detail = template.content.firstElementChild.cloneNode(true);
  detail.querySelector('[data-field="abstract"]').textContent =
    paper.abstract || "No abstract available.";
  const findings = detail.querySelector('[data-field="findings"]');
  for (const finding of paper.aisummary?.key_findings_json ?? []) {
    const li = document.createElement("li");
    li.textContent = finding;
    findings.appendChild(li);
  }
  const summary = paper.aisummary ?? {};
  detail.querySelector('[data-field="dataset"]').textContent =
    summary.dataset_used ?? "—";
  detail.querySelector('[data-field="architecture"]').textContent =
    summary.model_architecture ?? "—";
  detail.querySelector('[data-field="sample-size"]').textContent =
    summary.sample_size ?? "—";
  detail.querySelector('[data-field="metrics"]').textContent =
    summary.reported_metrics ?? "—";
  detail.querySelector('[data-field="pubmed-link"]').href =
    `https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/`;
  const action = paper.user_action ?? {};
  detail.querySelector('[data-field="tags-input"]').value =
    (action.custom_tags_json ?? []).join(", ");
  detail.querySelector('[data-field="notes-input"]').value =
    action.notes_text ?? "";
  container.replaceChildren(detail);
}

async function toggleDetail(card) {
  const container = card.querySelector(".paper-detail");
  if (!container.hidden) {
    container.hidden = true;
    return;
  }
  if (!container.dataset.loaded) {
    try {
      const paper = await apiFetch(`/api/papers/${card.dataset.paperId}/`);
      fillDetail(container, paper);
      container.dataset.loaded = "1";
    } catch (err) {
      console.error(err);
      container.textContent = errorMessage(err);
    }
  }
  container.hidden = false;
}

async function handleAction(card, button) {
  const paperId = card.dataset.paperId;
  const kind = button.dataset.action;
  try {
    if (kind === "bookmark") {
      const indicator = card.querySelector('[data-field="bookmark"]');
      const next = indicator.hidden;
      indicator.hidden = !next;
      try {
        await patchAction(paperId, { is_bookmarked: next });
      } catch (err) {
        indicator.hidden = next;
        throw err;
      }
    } else if (kind === "read") {
      const next = !card.classList.contains("is-read");
      card.classList.toggle("is-read", next);
      try {
        await patchAction(paperId, { is_read: next });
      } catch (err) {
        card.classList.toggle("is-read", !next);
        throw err;
      }
    } else if (kind === "dismiss") {
      await patchAction(paperId, { is_dismissed: true });
      card.remove();
    } else if (kind === "save-tags") {
      const raw = card.querySelector('[data-field="tags-input"]').value;
      const tags = raw.split(",").map((tag) => tag.trim()).filter(Boolean);
      await patchAction(paperId, { custom_tags_json: tags });
    } else if (kind === "save-notes") {
      const notes = card.querySelector('[data-field="notes-input"]').value;
      await patchAction(paperId, { notes_text: notes });
    }
  } catch (err) {
    console.error(err);
    showError(card, errorMessage(err));
  }
}

export function initPaperInteractions() {
  document.getElementById("feed").addEventListener("click", (event) => {
    const card = event.target.closest(".paper-card");
    if (!card) return;
    const button = event.target.closest("[data-action]");
    if (button) {
      handleAction(card, button);
      return;
    }
    if (event.target.closest(".paper-detail")) return;
    if (event.target.closest("a")) return;
    toggleDetail(card);
  });
}
```

- [ ] **Step 2: Verify**

Run: `cd /workspace/backend && uv run python manage.py findstatic js/paper.js`
Expected: found.

Run: `cd /workspace/backend && uv run pytest -q && uv run ruff check .`
Expected: 146 passed, clean.

- [ ] **Step 3: Commit**

```bash
cd /workspace && git add backend/static/js/paper.js
git commit -m "feat: add paper expansion and user-action JS

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Final verification and smoke test

**Files:** none (verification only)

- [ ] **Step 1: Full gates**

Run: `cd /workspace/backend && uv run pytest -q && uv run ruff check .`
Expected: 146 passed, clean.

- [ ] **Step 2: Server smoke test**

```bash
cd /workspace/backend && uv run python manage.py migrate
cd /workspace/backend && nohup uv run python manage.py runserver 0.0.0.0:8000 > /tmp/runserver-p3.log 2>&1 &
sleep 30
```

Then with a registered session (same curl-cookie technique as Phase 2's smoke
test — fetch `/register/` for the csrf token, POST register, keep the cookie
jar):

1. `GET /radars/` (with session cookie) → 200, contains `data-radar-fetch`
1. `GET /api/papers/?min_score=3` → 200 JSON
1. `GET /api/papers/?search=test` → 200 JSON
1. `GET /api/papers/?date_from=not-a-date` → 200 (graceful)
1. `GET /static/js/filters.js`, `feed.js`, `paper.js` → 200
1. `GET /` (with session) → 200, contains `paper-card-template`
1. Kill the server.

- [ ] **Step 3: Manual browser checklist (report as remaining human QA)**

- Log in → dashboard loads radars in sidebar and papers in feed
- Change a filter → feed refreshes; search debounces
- Click a card → detail expands with abstract/findings/PubMed link
- Bookmark/read/dismiss → state changes; dismissed card disappears
- Save tags and notes → reload page → values persist
- Radars page → create/edit/delete radar; Fetch now → "Queued ✓"

- [ ] **Step 4: Report**

Run: `cd /workspace && git status --short` and report final state.
