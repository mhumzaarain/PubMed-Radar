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
