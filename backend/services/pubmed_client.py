import xml.etree.ElementTree as ET
from datetime import date
from typing import Optional

import requests

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

MONTH_ABBR = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def search_pmids(query: str, date_from: Optional[date] = None, max_results: int = 100) -> list[str]:
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
    }
    if date_from:
        params["mindate"] = date_from.strftime("%Y/%m/%d")
        params["datetype"] = "pdat"
    response = requests.get(f"{EUTILS_BASE}esearch.fcgi", params=params, timeout=30)
    response.raise_for_status()
    return response.json()["esearchresult"]["idlist"]


def fetch_papers(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "abstract",
        "retmode": "xml",
    }
    response = requests.get(f"{EUTILS_BASE}efetch.fcgi", params=params, timeout=60)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    return [_parse_article(article) for article in root.findall("PubmedArticle")]


def _parse_article(article: ET.Element) -> dict:
    medline = article.find("MedlineCitation")
    art = medline.find("Article")

    pmid = (medline.findtext("PMID") or "").strip()
    title = (art.findtext("ArticleTitle") or "").strip()
    journal = (art.findtext("Journal/Title") or "").strip()

    authors = []
    for author in art.findall("AuthorList/Author"):
        last = author.findtext("LastName") or ""
        first = author.findtext("ForeName") or ""
        if last:
            name = f"{last}, {first}".strip(", ")
            authors.append(name)

    doi = None
    for loc in art.findall("ELocationID"):
        if loc.get("EIdType") == "doi":
            doi = loc.text
            break

    abstract_parts = [el.text or "" for el in art.findall("Abstract/AbstractText")]
    abstract = "\n\n".join(p for p in abstract_parts if p)

    pub_date_el = art.find("Journal/JournalIssue/PubDate")
    publication_date = _parse_pub_date(pub_date_el)

    pub_types = art.findall("PublicationTypeList/PublicationType")
    article_type = pub_types[0].text if pub_types else ""

    return {
        "pmid": pmid,
        "title": title,
        "authors": authors,
        "journal": journal,
        "doi": doi,
        "abstract": abstract,
        "publication_date": publication_date,
        "article_type": article_type,
    }


def _parse_pub_date(pub_date_el: Optional[ET.Element]) -> date:
    if pub_date_el is None:
        return date.today()
    year = int(pub_date_el.findtext("Year") or date.today().year)
    month_raw = pub_date_el.findtext("Month") or "1"
    try:
        month = int(month_raw)
    except ValueError:
        month = MONTH_ABBR.get(month_raw[:3].capitalize(), 1)
    day_raw = pub_date_el.findtext("Day")
    day = int(day_raw) if day_raw else 1
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, month, 1)
