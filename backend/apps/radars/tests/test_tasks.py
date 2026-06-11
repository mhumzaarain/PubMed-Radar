import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.papers.factories import AISummaryFactory, PaperFactory, PaperRadarFactory
from apps.papers.models import Paper, PaperRadar
from apps.radars.factories import RadarFactory
from apps.radars.models import Radar
from apps.radars.tasks import defer_fetch, dispatch_due_radars, fetch_radar, fetch_radar_task

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

    def test_retry_does_not_duplicate_summarize_jobs(self, procrastinate_in_memory):
        radar = RadarFactory()
        search, fetch = _patch_pubmed(["38000001"], [SAMPLE_PAPER_DICT])
        with search, fetch:
            fetch_radar_task(radar_id=str(radar.id))
            fetch_radar_task(radar_id=str(radar.id))
        assert len(_jobs(procrastinate_in_memory, SUMMARIZE_TASK)) == 1


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
