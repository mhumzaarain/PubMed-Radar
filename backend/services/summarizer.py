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
