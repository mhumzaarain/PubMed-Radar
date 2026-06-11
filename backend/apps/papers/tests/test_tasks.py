import uuid
from unittest.mock import patch

import pytest

from apps.papers.factories import AISummaryFactory, PaperFactory
from apps.papers.models import AISummary
from apps.papers.tasks import summarize_paper_task
from services.summarizer import SummarizationError

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

    def test_summarization_error_propagates_for_retry(self):
        paper = PaperFactory()
        with (
            patch(
                "apps.papers.tasks.summarizer.summarize",
                side_effect=SummarizationError("bad JSON"),
            ),
            pytest.raises(SummarizationError),
        ):
            summarize_paper_task(paper_id=str(paper.id))
        assert AISummary.objects.count() == 0
