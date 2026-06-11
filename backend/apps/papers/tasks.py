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
