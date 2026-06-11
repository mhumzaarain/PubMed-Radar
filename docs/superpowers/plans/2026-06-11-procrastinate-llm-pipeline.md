# Procrastinate + LLM Summarization Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Background-process radar fetches with Procrastinate (hourly dispatcher honoring per-radar daily/weekly schedules) and populate `AISummary` via an LLM summarizer that works with any OpenAI-compatible endpoint.

**Architecture:** A periodic Procrastinate task (`dispatch_due_radars`, hourly cron) queries the DB for due radars and defers `fetch_radar_task` per radar. The fetch task wraps the existing `fetch_radar()` function, then defers `summarize_paper_task` for every paper in the radar with a non-empty abstract and no `AISummary`. Jobs live in PostgreSQL (no broker). The manual fetch endpoint becomes async (202).

**Tech Stack:** Django 5.1, DRF, Procrastinate 3.x (`procrastinate.contrib.django`), `openai` client against `LLM_BASE_URL`, psycopg 3, pytest + factory-boy, uv.

**Spec:** `docs/superpowers/specs/2026-06-11-procrastinate-llm-pipeline-design.md`

**Conventions used throughout:**

- All commands run from `/workspace/backend` with `uv run`.
- Procrastinate task functions are directly callable in tests (calling the decorated task runs the wrapped function synchronously).
- Deferred-job assertions use the `procrastinate_in_memory` fixture (added in Task 3); inspect jobs via `procrastinate_in_memory.connector.jobs` (dict of job-id → job dict with `task_name` and `args` keys).
- UUIDs are passed to `.defer()` as strings (job args must be JSON-serializable).

---

### Task 1: Dependencies and Procrastinate wiring

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/config/settings.py`

- [ ] **Step 1: Update dependencies in `backend/pyproject.toml`**

Replace the `psycopg2-binary` line and add two new dependencies. The `dependencies` list becomes:

```toml
dependencies = [
    "django==5.1.4",
    "djangorestframework==3.15.2",
    "djangorestframework-simplejwt==5.3.1",
    "django-cors-headers==4.6.0",
    "psycopg[binary]>=3.2",
    "python-decouple==3.8",
    "requests>=2.31",
    "procrastinate[django]>=3.0",
    "openai>=1.50",
]
```

- [ ] **Step 2: Install**

Run: `cd /workspace/backend && uv sync --extra dev`
Expected: resolves and installs `procrastinate`, `openai`, `psycopg`; removes `psycopg2-binary`. `uv.lock` is updated.

- [ ] **Step 3: Register the Procrastinate Django app**

In `backend/config/settings.py`, change `THIRD_PARTY_APPS` to (procrastinate placed before local apps, per its docs):

```python
THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "procrastinate.contrib.django",
]
```

- [ ] **Step 4: Apply Procrastinate's migrations**

Run: `cd /workspace/backend && uv run python manage.py migrate`
Expected: a series of `procrastinate.XXXX_...` migrations apply with `OK`. (Procrastinate ships its job-queue tables as ordinary Django migrations.)

- [ ] **Step 5: Verify nothing broke**

Run: `cd /workspace/backend && uv run pytest`
Expected: all existing tests PASS (the psycopg 2→3 swap is transparent to Django 5.1).

- [ ] **Step 6: Commit**

```bash
cd /workspace && git add backend/pyproject.toml backend/uv.lock backend/config/settings.py
git commit -m "feat: add procrastinate, openai, swap psycopg2 for psycopg3"
```

---

### Task 2: LLM settings and summarizer service

**Files:**
- Modify: `backend/config/settings.py` (append at end)
- Modify: `.env.example`
- Create: `backend/services/summarizer.py`
- Test: `backend/services/tests/test_summarizer.py`

- [ ] **Step 1: Add LLM settings**

Append to the end of `backend/config/settings.py`:

```python
# --- LLM (any OpenAI-compatible endpoint) ---
LLM_BASE_URL = config("LLM_BASE_URL", default="https://api.openai.com/v1")
LLM_API_KEY = config("LLM_API_KEY", default="")
LLM_MODEL = config("LLM_MODEL", default="gpt-4o-mini")
LLM_TIMEOUT = config("LLM_TIMEOUT", default=60, cast=int)
```

- [ ] **Step 2: Document the variables in `.env.example`**

Replace the trailing "External APIs" block of `/workspace/.env.example` with:

```bash
# External APIs
NCBI_API_KEY=

# LLM — any OpenAI-compatible endpoint
# OpenAI:  LLM_BASE_URL=https://api.openai.com/v1   LLM_MODEL=gpt-4o-mini
# Ollama:  LLM_BASE_URL=http://localhost:11434/v1   LLM_MODEL=llama3.1  LLM_API_KEY=ollama
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini
LLM_TIMEOUT=60
```

(The old `ANTHROPIC_API_KEY` line is superseded by the generic `LLM_*` config — remove it.)

- [ ] **Step 3: Write the failing tests**

Create `backend/services/tests/test_summarizer.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from services import summarizer
from services.summarizer import SummarizationError, parse_summary_response

VALID_RESPONSE = """
{
  "one_line_summary": "A deep learning model detects lung nodules on CT with high accuracy.",
  "key_findings": ["AUC of 0.94", "Outperformed radiologists"],
  "methodology": {
    "dataset": "LIDC-IDRI",
    "model_architecture": "3D CNN",
    "sample_size": 1018,
    "reported_metrics": "AUC 0.94"
  },
  "relevance_score": 4,
  "novelty_tag": "new_approach"
}
"""


class TestParseSummaryResponse:
    def test_parses_clean_json(self):
        data = parse_summary_response(VALID_RESPONSE)
        assert data["one_line_summary"].startswith("A deep learning model")
        assert data["key_findings_json"] == ["AUC of 0.94", "Outperformed radiologists"]
        assert data["dataset_used"] == "LIDC-IDRI"
        assert data["model_architecture"] == "3D CNN"
        assert data["sample_size"] == "1018"
        assert data["reported_metrics"] == "AUC 0.94"
        assert data["relevance_score"] == 4
        assert data["novelty_tag"] == "new_approach"

    def test_strips_markdown_fences(self):
        fenced = f"```json\n{VALID_RESPONSE.strip()}\n```"
        data = parse_summary_response(fenced)
        assert data["novelty_tag"] == "new_approach"

    def test_invalid_json_raises(self):
        with pytest.raises(SummarizationError):
            parse_summary_response("I'm sorry, I can't produce JSON today.")

    def test_non_object_json_raises(self):
        with pytest.raises(SummarizationError):
            parse_summary_response('["a", "list"]')

    def test_relevance_score_clamped_high(self):
        raw = VALID_RESPONSE.replace('"relevance_score": 4', '"relevance_score": 9')
        assert parse_summary_response(raw)["relevance_score"] == 5

    def test_relevance_score_clamped_low(self):
        raw = VALID_RESPONSE.replace('"relevance_score": 4', '"relevance_score": 0')
        assert parse_summary_response(raw)["relevance_score"] == 1

    def test_non_numeric_relevance_score_raises(self):
        raw = VALID_RESPONSE.replace('"relevance_score": 4', '"relevance_score": "high"')
        with pytest.raises(SummarizationError):
            parse_summary_response(raw)

    def test_invalid_novelty_tag_raises(self):
        with pytest.raises(SummarizationError):
            parse_summary_response(VALID_RESPONSE.replace("new_approach", "groundbreaking"))

    def test_missing_one_line_summary_raises(self):
        broken = VALID_RESPONSE.replace(
            '"one_line_summary": "A deep learning model detects lung nodules on CT with high accuracy.",',
            "",
        )
        with pytest.raises(SummarizationError):
            parse_summary_response(broken)

    def test_missing_methodology_fields_become_null(self):
        minimal = """
        {
          "one_line_summary": "Summary.",
          "key_findings": [],
          "relevance_score": 2,
          "novelty_tag": "review"
        }
        """
        data = parse_summary_response(minimal)
        assert data["dataset_used"] is None
        assert data["model_architecture"] is None
        assert data["sample_size"] is None
        assert data["reported_metrics"] is None
        assert data["key_findings_json"] == []


class TestSummarize:
    def test_calls_llm_and_returns_parsed_data(self, settings):
        settings.LLM_MODEL = "test-model"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=VALID_RESPONSE))]
        )
        paper = MagicMock(title="Lung nodules", journal="Radiology", abstract="An abstract.")
        with patch("services.summarizer._get_client", return_value=mock_client):
            data = summarizer.summarize(paper)
        assert data["novelty_tag"] == "new_approach"
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "test-model"
        prompt = call_kwargs["messages"][0]["content"]
        assert "Lung nodules" in prompt
        assert "Radiology" in prompt
        assert "An abstract." in prompt
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd /workspace/backend && uv run pytest services/tests/test_summarizer.py -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'services.summarizer'`

- [ ] **Step 5: Implement the summarizer**

Create `backend/services/summarizer.py`:

```python
import json

from django.conf import settings
from openai import OpenAI

NOVELTY_TAGS = {"incremental", "new_approach", "review", "benchmark", "dataset", "meta_analysis"}

PROMPT_TEMPLATE = """You are a medical research assistant. Given a PubMed paper abstract,
extract the following as JSON:

{{
  "one_line_summary": "Plain English summary in one sentence, max 30 words",
  "key_findings": ["Finding 1", "Finding 2", "Finding 3"],
  "methodology": {{
    "dataset": "Name of dataset used, or null",
    "model_architecture": "e.g., ResNet-50, U-Net, transformer, or null",
    "sample_size": "Number of patients/images/samples, or null",
    "reported_metrics": "e.g., AUC 0.95, sensitivity 92%, or null"
  }},
  "relevance_score": 3,
  "novelty_tag": "new_approach"
}}

"relevance_score" is an integer 1-5: how directly applicable to clinical practice.
"novelty_tag" is one of: incremental, new_approach, review, benchmark, dataset, meta_analysis.

Paper title: {title}
Journal: {journal}
Abstract: {abstract}

Respond ONLY with valid JSON. No markdown, no explanation."""


class SummarizationError(Exception):
    """The LLM response could not be parsed into a valid summary."""


def _get_client() -> OpenAI:
    return OpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        timeout=settings.LLM_TIMEOUT,
    )


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        text = "\n".join(lines).strip()
    return text


def _optional_str(value) -> str | None:
    if value is None:
        return None
    return str(value)


def parse_summary_response(text: str) -> dict:
    """Parse and validate LLM output into AISummary field values.

    Raises SummarizationError on anything unusable, so the calling task
    retries (a fresh sampling usually fixes malformed output).
    """
    try:
        data = json.loads(_strip_code_fences(text))
    except json.JSONDecodeError as exc:
        raise SummarizationError(f"LLM response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SummarizationError("LLM response JSON is not an object")

    one_line_summary = str(data.get("one_line_summary") or "").strip()
    if not one_line_summary:
        raise SummarizationError("Missing one_line_summary")

    novelty_tag = data.get("novelty_tag")
    if novelty_tag not in NOVELTY_TAGS:
        raise SummarizationError(f"Invalid novelty_tag: {novelty_tag!r}")

    try:
        relevance_score = int(data.get("relevance_score"))
    except (TypeError, ValueError) as exc:
        raise SummarizationError(
            f"Invalid relevance_score: {data.get('relevance_score')!r}"
        ) from exc
    relevance_score = max(1, min(5, relevance_score))

    key_findings = data.get("key_findings") or []
    if not isinstance(key_findings, list):
        raise SummarizationError("key_findings is not a list")

    methodology = data.get("methodology") or {}
    if not isinstance(methodology, dict):
        methodology = {}

    return {
        "one_line_summary": one_line_summary,
        "key_findings_json": [str(item) for item in key_findings],
        "dataset_used": _optional_str(methodology.get("dataset")),
        "model_architecture": _optional_str(methodology.get("model_architecture")),
        "sample_size": _optional_str(methodology.get("sample_size")),
        "reported_metrics": _optional_str(methodology.get("reported_metrics")),
        "relevance_score": relevance_score,
        "novelty_tag": novelty_tag,
    }


def summarize(paper) -> dict:
    """Send a paper's abstract to the configured LLM, return AISummary field values."""
    prompt = PROMPT_TEMPLATE.format(
        title=paper.title, journal=paper.journal, abstract=paper.abstract
    )
    client = _get_client()
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content or ""
    return parse_summary_response(content)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /workspace/backend && uv run pytest services/tests/test_summarizer.py -v`
Expected: all 11 tests PASS

- [ ] **Step 7: Lint and commit**

```bash
cd /workspace/backend && uv run ruff check services/
cd /workspace && git add backend/services/summarizer.py backend/services/tests/test_summarizer.py backend/config/settings.py .env.example
git commit -m "feat: add LLM summarizer service for OpenAI-compatible endpoints"
```

---

### Task 3: Procrastinate test fixture and summarize_paper_task

**Files:**
- Modify: `backend/conftest.py`
- Create: `backend/apps/papers/tasks.py`
- Test: `backend/apps/papers/tests/test_tasks.py`

- [ ] **Step 1: Add the in-memory Procrastinate fixture**

Append to `backend/conftest.py` (and add the two imports to the top of the file):

```python
from procrastinate import testing
from procrastinate.contrib.django import procrastinate_app


@pytest.fixture
def procrastinate_in_memory():
    """Procrastinate app backed by an in-memory connector.

    Deferred jobs are visible via `procrastinate_in_memory.connector.jobs`
    (dict of job-id -> job dict) instead of hitting the database.
    """
    in_memory = testing.InMemoryConnector()
    with procrastinate_app.current_app.replace_connector(in_memory) as app:
        yield app
```

- [ ] **Step 2: Write the failing tests**

Create `backend/apps/papers/tests/test_tasks.py`:

```python
import uuid
from unittest.mock import patch

import pytest

from apps.papers.factories import AISummaryFactory, PaperFactory
from apps.papers.models import AISummary
from apps.papers.tasks import summarize_paper_task

SUMMARY_DATA = {
    "one_line_summary": "Test summary.",
    "key_findings_json": ["Finding 1"],
    "dataset_used": None,
    "model_architecture": None,
    "sample_size": None,
    "reported_metrics": None,
    "relevance_score": 3,
    "novelty_tag": "incremental",
}


@pytest.mark.django_db
class TestSummarizePaperTask:
    def test_creates_summary(self, settings):
        settings.LLM_MODEL = "test-model"
        paper = PaperFactory()
        with patch("apps.papers.tasks.summarizer.summarize", return_value=dict(SUMMARY_DATA)):
            summarize_paper_task(paper_id=str(paper.id))
        summary = AISummary.objects.get(paper=paper)
        assert summary.one_line_summary == "Test summary."
        assert summary.relevance_score == 3
        assert summary.model_used == "test-model"

    def test_skips_when_summary_exists(self):
        existing = AISummaryFactory()
        with patch("apps.papers.tasks.summarizer.summarize") as mock_summarize:
            summarize_paper_task(paper_id=str(existing.paper.id))
        mock_summarize.assert_not_called()
        assert AISummary.objects.count() == 1

    def test_missing_paper_is_noop(self):
        with patch("apps.papers.tasks.summarizer.summarize") as mock_summarize:
            summarize_paper_task(paper_id=str(uuid.uuid4()))
        mock_summarize.assert_not_called()
        assert AISummary.objects.count() == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /workspace/backend && uv run pytest apps/papers/tests/test_tasks.py -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'apps.papers.tasks'`

- [ ] **Step 4: Implement the task**

Create `backend/apps/papers/tasks.py`:

```python
import logging

from django.conf import settings
from procrastinate import RetryStrategy
from procrastinate.contrib.django import app

from services import summarizer

from .models import AISummary, Paper

logger = logging.getLogger(__name__)


@app.task(retry=RetryStrategy(max_attempts=5, exponential_wait=10))
def summarize_paper_task(paper_id: str):
    """Generate and store the AISummary for one paper. Idempotent."""
    try:
        paper = Paper.objects.get(id=paper_id)
    except Paper.DoesNotExist:
        logger.warning("Paper %s no longer exists, skipping summarization", paper_id)
        return
    if AISummary.objects.filter(paper=paper).exists():
        return
    data = summarizer.summarize(paper)
    AISummary.objects.create(paper=paper, model_used=settings.LLM_MODEL, **data)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /workspace/backend && uv run pytest apps/papers/tests/test_tasks.py -v`
Expected: 3 tests PASS

- [ ] **Step 6: Lint and commit**

```bash
cd /workspace/backend && uv run ruff check apps/ conftest.py
cd /workspace && git add backend/conftest.py backend/apps/papers/tasks.py backend/apps/papers/tests/test_tasks.py
git commit -m "feat: add summarize_paper_task with retry and idempotency"
```

---

### Task 4: fetch_radar_task and defer_fetch

**Files:**
- Modify: `backend/apps/radars/tasks.py`
- Test: `backend/apps/radars/tests/test_tasks.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/apps/radars/tests/test_tasks.py`:

```python
import uuid
from datetime import date
from unittest.mock import patch

import pytest

from apps.papers.factories import AISummaryFactory, PaperFactory, PaperRadarFactory
from apps.papers.models import Paper, PaperRadar
from apps.radars.factories import RadarFactory
from apps.radars.tasks import defer_fetch, fetch_radar, fetch_radar_task

SAMPLE_PAPER_DICT = {
    "pmid": "38000001",
    "title": "Test Paper",
    "authors": ["Smith, John"],
    "journal": "Nature Medicine",
    "doi": "10.1038/test",
    "abstract": "Test abstract.",
    "publication_date": date(2024, 1, 15),
    "article_type": "Journal Article",
}

SUMMARIZE_TASK = "apps.papers.tasks.summarize_paper_task"
FETCH_TASK = "apps.radars.tasks.fetch_radar_task"


def _patch_pubmed(pmids, papers):
    return (
        patch("apps.radars.tasks.pubmed_client.search_pmids", return_value=pmids),
        patch("apps.radars.tasks.pubmed_client.fetch_papers", return_value=papers),
    )


def _jobs(app, task_name):
    return [j for j in app.connector.jobs.values() if j["task_name"] == task_name]


@pytest.mark.django_db
class TestFetchRadarFunction:
    def test_creates_papers_and_links_radar(self):
        radar = RadarFactory()
        search, fetch = _patch_pubmed(["38000001"], [SAMPLE_PAPER_DICT])
        with search, fetch:
            new_count = fetch_radar(radar.id)
        assert new_count == 1
        assert Paper.objects.count() == 1
        assert PaperRadar.objects.filter(radar=radar).count() == 1

    def test_deduplicates_on_second_run(self):
        radar = RadarFactory()
        search, fetch = _patch_pubmed(["38000001"], [SAMPLE_PAPER_DICT])
        with search, fetch:
            fetch_radar(radar.id)
            new_count = fetch_radar(radar.id)
        assert new_count == 0
        assert Paper.objects.count() == 1
        assert PaperRadar.objects.count() == 1

    def test_updates_last_fetched_at(self):
        radar = RadarFactory()
        assert radar.last_fetched_at is None
        search, fetch = _patch_pubmed([], [])
        with search, fetch:
            fetch_radar(radar.id)
        radar.refresh_from_db()
        assert radar.last_fetched_at is not None


@pytest.mark.django_db
class TestFetchRadarTask:
    def test_fetches_and_defers_summaries(self, procrastinate_in_memory):
        radar = RadarFactory()
        search, fetch = _patch_pubmed(["38000001"], [SAMPLE_PAPER_DICT])
        with search, fetch:
            fetch_radar_task(radar_id=str(radar.id))
        paper = Paper.objects.get(pmid="38000001")
        jobs = _jobs(procrastinate_in_memory, SUMMARIZE_TASK)
        assert len(jobs) == 1
        assert jobs[0]["args"] == {"paper_id": str(paper.id)}

    def test_skips_already_summarized_papers(self, procrastinate_in_memory):
        radar = RadarFactory()
        paper = PaperFactory(pmid="38000001")
        PaperRadarFactory(paper=paper, radar=radar)
        AISummaryFactory(paper=paper)
        search, fetch = _patch_pubmed(["38000001"], [SAMPLE_PAPER_DICT])
        with search, fetch:
            fetch_radar_task(radar_id=str(radar.id))
        assert _jobs(procrastinate_in_memory, SUMMARIZE_TASK) == []

    def test_skips_papers_with_empty_abstract(self, procrastinate_in_memory):
        radar = RadarFactory()
        no_abstract = dict(SAMPLE_PAPER_DICT, abstract="")
        search, fetch = _patch_pubmed(["38000001"], [no_abstract])
        with search, fetch:
            fetch_radar_task(radar_id=str(radar.id))
        assert _jobs(procrastinate_in_memory, SUMMARIZE_TASK) == []

    def test_redefer_papers_missing_summary_from_previous_run(self, procrastinate_in_memory):
        """Self-healing: an unsummarized paper from an earlier fetch is re-deferred."""
        radar = RadarFactory()
        old_paper = PaperFactory(abstract="Old but unsummarized.")
        PaperRadarFactory(paper=old_paper, radar=radar)
        search, fetch = _patch_pubmed([], [])
        with search, fetch:
            fetch_radar_task(radar_id=str(radar.id))
        jobs = _jobs(procrastinate_in_memory, SUMMARIZE_TASK)
        assert len(jobs) == 1
        assert jobs[0]["args"] == {"paper_id": str(old_paper.id)}

    def test_deleted_radar_is_noop(self, procrastinate_in_memory):
        fetch_radar_task(radar_id=str(uuid.uuid4()))
        assert procrastinate_in_memory.connector.jobs == {}


@pytest.mark.django_db
class TestDeferFetch:
    def test_defers_fetch_job(self, procrastinate_in_memory):
        radar = RadarFactory()
        defer_fetch(radar.id)
        jobs = _jobs(procrastinate_in_memory, FETCH_TASK)
        assert len(jobs) == 1
        assert jobs[0]["args"] == {"radar_id": str(radar.id)}

    def test_duplicate_defer_is_queued_once(self, procrastinate_in_memory):
        radar = RadarFactory()
        defer_fetch(radar.id)
        defer_fetch(radar.id)
        assert len(_jobs(procrastinate_in_memory, FETCH_TASK)) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /workspace/backend && uv run pytest apps/radars/tests/test_tasks.py -v`
Expected: FAIL at collection — `ImportError: cannot import name 'defer_fetch' from 'apps.radars.tasks'`

- [ ] **Step 3: Implement the tasks**

Replace `backend/apps/radars/tasks.py` with (keeps `fetch_radar()` byte-identical, adds the rest):

```python
import logging
from datetime import timedelta

from django.utils import timezone
from procrastinate import RetryStrategy
from procrastinate.contrib.django import app
from procrastinate.exceptions import AlreadyEnqueued

from apps.papers.models import Paper, PaperRadar
from apps.papers.tasks import summarize_paper_task
from apps.radars.models import Radar
from services import pubmed_client

logger = logging.getLogger(__name__)


def fetch_radar(radar_id) -> int:
    radar = Radar.objects.get(id=radar_id)

    if radar.last_fetched_at:
        date_from = radar.last_fetched_at.date()
    else:
        date_from = (timezone.now() - timedelta(days=30)).date()

    pmids = pubmed_client.search_pmids(
        query=radar.pubmed_query,
        date_from=date_from,
        max_results=100,
    )

    paper_dicts = pubmed_client.fetch_papers(pmids)

    new_count = 0
    for pd in paper_dicts:
        paper, created = Paper.objects.get_or_create(
            pmid=pd["pmid"],
            defaults={
                "title": pd["title"],
                "authors_json": pd["authors"],
                "journal": pd["journal"],
                "doi": pd["doi"],
                "abstract": pd["abstract"],
                "publication_date": pd["publication_date"],
                "article_type": pd["article_type"],
            },
        )
        PaperRadar.objects.get_or_create(paper=paper, radar=radar)
        if created:
            new_count += 1

    radar.last_fetched_at = timezone.now()
    radar.save(update_fields=["last_fetched_at"])

    return new_count


@app.task(retry=RetryStrategy(max_attempts=3, exponential_wait=5))
def fetch_radar_task(radar_id: str):
    """Fetch new papers for a radar, then queue summarization for any paper
    in this radar that has an abstract but no AISummary yet (including ones
    left over from previously failed summarization jobs — this is what makes
    the pipeline self-healing)."""
    try:
        fetch_radar(radar_id)
    except Radar.DoesNotExist:
        logger.warning("Radar %s no longer exists, skipping fetch", radar_id)
        return

    unsummarized = Paper.objects.filter(
        paper_radars__radar__id=radar_id, aisummary__isnull=True
    ).exclude(abstract="")
    for paper in unsummarized:
        summarize_paper_task.defer(paper_id=str(paper.id))


def defer_fetch(radar_id) -> None:
    """Queue a fetch for a radar; no-op if one is already queued."""
    try:
        fetch_radar_task.configure(queueing_lock=f"fetch-radar-{radar_id}").defer(
            radar_id=str(radar_id)
        )
    except AlreadyEnqueued:
        logger.info("Fetch for radar %s already queued, skipping", radar_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /workspace/backend && uv run pytest apps/radars/tests/test_tasks.py -v`
Expected: 10 tests PASS

- [ ] **Step 5: Confirm the old endpoint tests still pass (view unchanged so far)**

Run: `cd /workspace/backend && uv run pytest apps/radars/ -v`
Expected: all PASS (`test_fetch_action.py` still exercises the synchronous path until Task 6)

- [ ] **Step 6: Lint and commit**

```bash
cd /workspace/backend && uv run ruff check apps/radars/
cd /workspace && git add backend/apps/radars/tasks.py backend/apps/radars/tests/test_tasks.py
git commit -m "feat: add fetch_radar_task with summarization deferral and queueing lock"
```

---

### Task 5: Periodic dispatcher

**Files:**
- Modify: `backend/apps/radars/tasks.py` (append)
- Test: `backend/apps/radars/tests/test_tasks.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/radars/tests/test_tasks.py`. First update the imports at the top of the file: change the existing `from datetime import date` line to `from datetime import date, timedelta`, change `from apps.radars.tasks import defer_fetch, fetch_radar, fetch_radar_task` to also import `dispatch_due_radars`, and add:

```python
from django.utils import timezone

from apps.radars.models import Radar
```

Then append the test class:

```python
@pytest.mark.django_db
class TestDispatchDueRadars:
    def test_never_fetched_radar_is_dispatched(self, procrastinate_in_memory):
        radar = RadarFactory(last_fetched_at=None)
        dispatch_due_radars(timestamp=0)
        jobs = _jobs(procrastinate_in_memory, FETCH_TASK)
        assert len(jobs) == 1
        assert jobs[0]["args"] == {"radar_id": str(radar.id)}

    def test_overdue_daily_dispatched_recent_daily_not(self, procrastinate_in_memory):
        now = timezone.now()
        overdue = RadarFactory(schedule=Radar.DAILY, last_fetched_at=now - timedelta(hours=25))
        RadarFactory(schedule=Radar.DAILY, last_fetched_at=now - timedelta(hours=1))
        dispatch_due_radars(timestamp=0)
        jobs = _jobs(procrastinate_in_memory, FETCH_TASK)
        assert len(jobs) == 1
        assert jobs[0]["args"] == {"radar_id": str(overdue.id)}

    def test_weekly_not_due_after_three_days(self, procrastinate_in_memory):
        now = timezone.now()
        RadarFactory(schedule=Radar.WEEKLY, last_fetched_at=now - timedelta(days=3))
        dispatch_due_radars(timestamp=0)
        assert _jobs(procrastinate_in_memory, FETCH_TASK) == []

    def test_weekly_due_after_eight_days(self, procrastinate_in_memory):
        now = timezone.now()
        radar = RadarFactory(schedule=Radar.WEEKLY, last_fetched_at=now - timedelta(days=8))
        dispatch_due_radars(timestamp=0)
        jobs = _jobs(procrastinate_in_memory, FETCH_TASK)
        assert len(jobs) == 1
        assert jobs[0]["args"] == {"radar_id": str(radar.id)}

    def test_inactive_radar_excluded(self, procrastinate_in_memory):
        RadarFactory(is_active=False, last_fetched_at=None)
        dispatch_due_radars(timestamp=0)
        assert _jobs(procrastinate_in_memory, FETCH_TASK) == []

    def test_double_dispatch_queues_each_radar_once(self, procrastinate_in_memory):
        RadarFactory(last_fetched_at=None)
        dispatch_due_radars(timestamp=0)
        dispatch_due_radars(timestamp=3600)
        assert len(_jobs(procrastinate_in_memory, FETCH_TASK)) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /workspace/backend && uv run pytest apps/radars/tests/test_tasks.py -v`
Expected: FAIL at collection — `ImportError: cannot import name 'dispatch_due_radars'`

- [ ] **Step 3: Implement the dispatcher**

In `backend/apps/radars/tasks.py`, add `Q` to the Django imports:

```python
from django.db.models import Q
```

Then append:

```python
SCHEDULE_INTERVALS = {
    Radar.DAILY: timedelta(hours=24),
    Radar.WEEKLY: timedelta(days=7),
}


@app.periodic(cron="0 * * * *")
@app.task
def dispatch_due_radars(timestamp: int):
    """Hourly heartbeat: queue a fetch for every active radar whose schedule
    interval has elapsed since last_fetched_at (or that has never been fetched)."""
    now = timezone.now()
    due = Radar.objects.filter(is_active=True).filter(
        Q(last_fetched_at__isnull=True)
        | Q(schedule=Radar.DAILY, last_fetched_at__lt=now - SCHEDULE_INTERVALS[Radar.DAILY])
        | Q(schedule=Radar.WEEKLY, last_fetched_at__lt=now - SCHEDULE_INTERVALS[Radar.WEEKLY])
    )
    for radar in due:
        defer_fetch(radar.id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /workspace/backend && uv run pytest apps/radars/tests/test_tasks.py -v`
Expected: 16 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
cd /workspace/backend && uv run ruff check apps/radars/
cd /workspace && git add backend/apps/radars/tasks.py backend/apps/radars/tests/test_tasks.py
git commit -m "feat: add hourly dispatcher honoring per-radar schedules"
```

---

### Task 6: Async fetch endpoint (202)

**Files:**
- Modify: `backend/apps/radars/views.py`
- Modify: `backend/apps/radars/tests/test_fetch_action.py` (rewrite)

- [ ] **Step 1: Rewrite the endpoint tests for async behavior**

Replace the entire content of `backend/apps/radars/tests/test_fetch_action.py` with (the synchronous pipeline behavior these tests used to cover now lives in `TestFetchRadarFunction` in `test_tasks.py`):

```python
import pytest

from apps.radars.factories import RadarFactory
from apps.users.factories import UserFactory

RADARS_URL = "/api/radars/"
FETCH_TASK = "apps.radars.tasks.fetch_radar_task"


def _fetch_jobs(app):
    return [j for j in app.connector.jobs.values() if j["task_name"] == FETCH_TASK]


@pytest.mark.django_db
class TestFetchAction:
    def test_fetch_returns_202_and_queues_job(self, auth_client, procrastinate_in_memory):
        client, user = auth_client
        radar = RadarFactory(user=user)
        response = client.post(f"{RADARS_URL}{radar.id}/fetch/")
        assert response.status_code == 202
        assert response.data == {"status": "queued"}
        jobs = _fetch_jobs(procrastinate_in_memory)
        assert len(jobs) == 1
        assert jobs[0]["args"] == {"radar_id": str(radar.id)}

    def test_duplicate_fetch_still_202_but_queued_once(self, auth_client, procrastinate_in_memory):
        client, user = auth_client
        radar = RadarFactory(user=user)
        client.post(f"{RADARS_URL}{radar.id}/fetch/")
        response = client.post(f"{RADARS_URL}{radar.id}/fetch/")
        assert response.status_code == 202
        assert len(_fetch_jobs(procrastinate_in_memory)) == 1

    def test_fetch_other_users_radar_returns_404(self, auth_client):
        client, _ = auth_client
        other_radar = RadarFactory(user=UserFactory())
        response = client.post(f"{RADARS_URL}{other_radar.id}/fetch/")
        assert response.status_code == 404

    def test_fetch_unauthenticated(self, api_client):
        radar = RadarFactory()
        response = api_client.post(f"{RADARS_URL}{radar.id}/fetch/")
        assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd /workspace/backend && uv run pytest apps/radars/tests/test_fetch_action.py -v`
Expected: `test_fetch_returns_202_and_queues_job` and `test_duplicate_fetch_still_202_but_queued_once` FAIL (endpoint still returns 200 with `new_papers`); the 404/401 tests PASS.

- [ ] **Step 3: Update the view**

Replace the entire content of `backend/apps/radars/views.py` with:

```python
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Radar
from .serializers import RadarSerializer
from .tasks import defer_fetch


class RadarViewSet(viewsets.ModelViewSet):
    serializer_class = RadarSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Radar.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"], url_path="fetch")
    def fetch(self, request, pk=None):
        radar = self.get_object()
        defer_fetch(radar.id)
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /workspace/backend && uv run pytest apps/radars/tests/test_fetch_action.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Lint and commit**

```bash
cd /workspace/backend && uv run ruff check apps/radars/
cd /workspace && git add backend/apps/radars/views.py backend/apps/radars/tests/test_fetch_action.py
git commit -m "feat: make manual radar fetch asynchronous, return 202"
```

---

### Task 7: Worker service and final verification

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add the worker service**

In `/workspace/docker-compose.yml`, add after the `web` service (same indentation level):

```yaml
  worker:
    build:
      context: ./backend
    command: python manage.py procrastinate worker
    volumes:
      - ./backend:/workspace/backend
    working_dir: /workspace/backend
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
```

- [ ] **Step 2: Validate compose file**

Run: `cd /workspace && docker compose config --quiet`
Expected: no output, exit code 0. (If docker isn't available in this environment, skip — YAML review in step 4's commit diff suffices.)

- [ ] **Step 3: Sanity-check the worker command exists**

Run: `cd /workspace/backend && uv run python manage.py procrastinate --help`
Expected: Procrastinate CLI help text listing the `worker` subcommand.

- [ ] **Step 4: Full test suite + lint**

Run: `cd /workspace/backend && uv run pytest && uv run ruff check .`
Expected: all tests PASS, no lint errors.

- [ ] **Step 5: Commit**

```bash
cd /workspace && git add docker-compose.yml
git commit -m "feat: add procrastinate worker service to docker-compose"
```
