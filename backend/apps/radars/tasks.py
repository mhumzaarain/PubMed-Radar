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
