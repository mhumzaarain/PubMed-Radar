from datetime import date
from unittest.mock import MagicMock, patch

from services.pubmed_client import fetch_papers, search_pmids

EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>38000001</PMID>
      <Article>
        <ArticleTitle>Test Paper Title</ArticleTitle>
        <Journal>
          <Title>Nature Medicine</Title>
          <JournalIssue>
            <PubDate><Year>2024</Year><Month>Jan</Month><Day>15</Day></PubDate>
          </JournalIssue>
        </Journal>
        <AuthorList>
          <Author><LastName>Smith</LastName><ForeName>John</ForeName></Author>
          <Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author>
        </AuthorList>
        <ELocationID EIdType="doi">10.1038/s41591-024-00001-0</ELocationID>
        <Abstract><AbstractText>This is the abstract.</AbstractText></Abstract>
        <PublicationTypeList>
          <PublicationType>Journal Article</PublicationType>
        </PublicationTypeList>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""


class TestSearchPmids:
    def test_returns_pmid_list(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"esearchresult": {"idlist": ["38000001", "38000002"]}}
        with patch("services.pubmed_client.requests.get", return_value=mock_resp) as mock_get:
            result = search_pmids("lung cancer AND CT")
        assert result == ["38000001", "38000002"]
        mock_get.assert_called_once()

    def test_passes_date_from(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"esearchresult": {"idlist": []}}
        with patch("services.pubmed_client.requests.get", return_value=mock_resp) as mock_get:
            search_pmids("query", date_from=date(2024, 1, 1))
        call_params = mock_get.call_args[1]["params"]
        assert call_params["mindate"] == "2024/01/01"
        assert call_params["datetype"] == "pdat"

    def test_no_date_from_omits_date_params(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"esearchresult": {"idlist": []}}
        with patch("services.pubmed_client.requests.get", return_value=mock_resp) as mock_get:
            search_pmids("query")
        call_params = mock_get.call_args[1]["params"]
        assert "mindate" not in call_params

    def test_empty_result(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"esearchresult": {"idlist": []}}
        with patch("services.pubmed_client.requests.get", return_value=mock_resp):
            assert search_pmids("obscure query") == []


class TestFetchPapers:
    def test_returns_empty_for_no_pmids(self):
        with patch("services.pubmed_client.requests.get") as mock_get:
            result = fetch_papers([])
        mock_get.assert_not_called()
        assert result == []

    def test_parses_paper_correctly(self):
        mock_resp = MagicMock()
        mock_resp.text = EFETCH_XML
        with patch("services.pubmed_client.requests.get", return_value=mock_resp):
            papers = fetch_papers(["38000001"])
        assert len(papers) == 1
        p = papers[0]
        assert p["pmid"] == "38000001"
        assert p["title"] == "Test Paper Title"
        assert p["journal"] == "Nature Medicine"
        assert p["authors"] == ["Smith, John", "Doe, Jane"]
        assert p["doi"] == "10.1038/s41591-024-00001-0"
        assert p["abstract"] == "This is the abstract."
        assert p["publication_date"] == date(2024, 1, 15)
        assert p["article_type"] == "Journal Article"

    def test_structured_abstract_joined(self):
        xml = EFETCH_XML.replace(
            "<Abstract><AbstractText>This is the abstract.</AbstractText></Abstract>",
            "<Abstract><AbstractText>Part 1.</AbstractText>"
            "<AbstractText>Part 2.</AbstractText></Abstract>",
        )
        mock_resp = MagicMock()
        mock_resp.text = xml
        with patch("services.pubmed_client.requests.get", return_value=mock_resp):
            papers = fetch_papers(["38000001"])
        assert papers[0]["abstract"] == "Part 1.\n\nPart 2."

    def test_missing_doi_returns_none(self):
        xml = EFETCH_XML.replace(
            '<ELocationID EIdType="doi">10.1038/s41591-024-00001-0</ELocationID>', ""
        )
        mock_resp = MagicMock()
        mock_resp.text = xml
        with patch("services.pubmed_client.requests.get", return_value=mock_resp):
            papers = fetch_papers(["38000001"])
        assert papers[0]["doi"] is None

    def test_month_abbreviation_parsed(self):
        xml = EFETCH_XML.replace(
            "<PubDate><Year>2024</Year><Month>Jan</Month><Day>15</Day></PubDate>",
            "<PubDate><Year>2023</Year><Month>Sep</Month><Day>3</Day></PubDate>",
        )
        mock_resp = MagicMock()
        mock_resp.text = xml
        with patch("services.pubmed_client.requests.get", return_value=mock_resp):
            papers = fetch_papers(["38000001"])
        assert papers[0]["publication_date"] == date(2023, 9, 3)

    def test_missing_day_defaults_to_1(self):
        xml = EFETCH_XML.replace(
            "<PubDate><Year>2024</Year><Month>Jan</Month><Day>15</Day></PubDate>",
            "<PubDate><Year>2024</Year><Month>Mar</Month></PubDate>",
        )
        mock_resp = MagicMock()
        mock_resp.text = xml
        with patch("services.pubmed_client.requests.get", return_value=mock_resp):
            papers = fetch_papers(["38000001"])
        assert papers[0]["publication_date"] == date(2024, 3, 1)
