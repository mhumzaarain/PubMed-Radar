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
        one_line_key = (
            '"one_line_summary": "A deep learning model detects lung nodules'
            ' on CT with high accuracy.",'
        )
        broken = VALID_RESPONSE.replace(one_line_key, "")
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

    def test_strips_single_line_fence(self):
        single_line = (
            '```json{"one_line_summary": "S.", "relevance_score": 2, "novelty_tag": "review"}```'
        )
        data = parse_summary_response(single_line)
        assert data["one_line_summary"] == "S."

    def test_boolean_relevance_score_raises(self):
        raw = VALID_RESPONSE.replace('"relevance_score": 4', '"relevance_score": true')
        with pytest.raises(SummarizationError):
            parse_summary_response(raw)


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
