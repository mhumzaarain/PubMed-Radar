from datetime import date
from unittest.mock import patch

import pytest

from apps.papers.models import Paper, PaperRadar
from apps.radars.factories import RadarFactory
from apps.users.factories import UserFactory

RADARS_URL = "/api/radars/"

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


@pytest.mark.django_db
class TestFetchAction:
    def test_fetch_creates_papers_and_returns_count(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        with (
            patch("apps.radars.tasks.pubmed_client.search_pmids", return_value=["38000001"]),
            patch("apps.radars.tasks.pubmed_client.fetch_papers", return_value=[SAMPLE_PAPER_DICT]),
        ):
            response = client.post(f"{RADARS_URL}{radar.id}/fetch/")
        assert response.status_code == 200
        assert response.data["new_papers"] == 1
        assert Paper.objects.count() == 1
        assert PaperRadar.objects.filter(radar=radar).count() == 1

    def test_fetch_empty_results_returns_zero(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        with (
            patch("apps.radars.tasks.pubmed_client.search_pmids", return_value=[]),
            patch("apps.radars.tasks.pubmed_client.fetch_papers", return_value=[]),
        ):
            response = client.post(f"{RADARS_URL}{radar.id}/fetch/")
        assert response.status_code == 200
        assert response.data["new_papers"] == 0

    def test_fetch_deduplicates_papers_on_second_run(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        mock_pmids = ["38000001"]
        mock_papers = [SAMPLE_PAPER_DICT]
        with (
            patch("apps.radars.tasks.pubmed_client.search_pmids", return_value=mock_pmids),
            patch("apps.radars.tasks.pubmed_client.fetch_papers", return_value=mock_papers),
        ):
            client.post(f"{RADARS_URL}{radar.id}/fetch/")
            response = client.post(f"{RADARS_URL}{radar.id}/fetch/")
        assert response.data["new_papers"] == 0
        assert Paper.objects.count() == 1
        assert PaperRadar.objects.count() == 1

    def test_fetch_updates_last_fetched_at(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        assert radar.last_fetched_at is None
        with (
            patch("apps.radars.tasks.pubmed_client.search_pmids", return_value=[]),
            patch("apps.radars.tasks.pubmed_client.fetch_papers", return_value=[]),
        ):
            client.post(f"{RADARS_URL}{radar.id}/fetch/")
        radar.refresh_from_db()
        assert radar.last_fetched_at is not None

    def test_fetch_other_users_radar_returns_404(self, auth_client):
        client, _ = auth_client
        other_radar = RadarFactory(user=UserFactory())
        response = client.post(f"{RADARS_URL}{other_radar.id}/fetch/")
        assert response.status_code == 404

    def test_fetch_unauthenticated(self, api_client):
        radar = RadarFactory()
        response = api_client.post(f"{RADARS_URL}{radar.id}/fetch/")
        assert response.status_code == 401
