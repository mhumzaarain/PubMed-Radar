import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.papers.factories import (
    AISummaryFactory,
    PaperFactory,
    PaperRadarFactory,
    UserPaperActionFactory,
)
from apps.radars.factories import RadarFactory
from apps.users.factories import UserFactory

PAPERS_URL = "/api/papers/"


def make_auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


@pytest.mark.django_db
class TestPaperList:
    def test_list_empty(self, auth_client):
        client, _ = auth_client
        response = client.get(PAPERS_URL)
        assert response.status_code == 200
        assert response.data["results"] == []

    def test_list_own_papers(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        PaperRadarFactory(radar=radar)
        PaperRadarFactory(radar=radar)
        response = client.get(PAPERS_URL)
        assert response.status_code == 200
        assert len(response.data["results"]) == 2

    def test_list_excludes_other_users_papers(self, auth_client):
        client, _ = auth_client
        other_radar = RadarFactory(user=UserFactory())
        PaperRadarFactory(radar=other_radar)
        response = client.get(PAPERS_URL)
        assert response.status_code == 200
        assert len(response.data["results"]) == 0

    def test_list_deduplicates_paper_in_multiple_radars(self, auth_client):
        client, user = auth_client
        radar1 = RadarFactory(user=user)
        radar2 = RadarFactory(user=user)
        paper = PaperFactory()
        PaperRadarFactory(paper=paper, radar=radar1)
        PaperRadarFactory(paper=paper, radar=radar2)
        response = client.get(PAPERS_URL)
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_list_filter_by_radar(self, auth_client):
        client, user = auth_client
        radar1 = RadarFactory(user=user)
        radar2 = RadarFactory(user=user)
        PaperRadarFactory(radar=radar1)
        PaperRadarFactory(radar=radar2)
        response = client.get(PAPERS_URL, {"radar": str(radar1.id)})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_list_filter_by_is_read(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr1 = PaperRadarFactory(radar=radar)
        pr2 = PaperRadarFactory(radar=radar)
        UserPaperActionFactory(user=user, paper=pr1.paper, is_read=True)
        UserPaperActionFactory(user=user, paper=pr2.paper, is_read=False)
        response = client.get(PAPERS_URL, {"is_read": "true"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["pmid"] == pr1.paper.pmid

    def test_list_filter_by_is_bookmarked(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        PaperRadarFactory(radar=radar)
        UserPaperActionFactory(user=user, paper=pr.paper, is_bookmarked=True)
        response = client.get(PAPERS_URL, {"is_bookmarked": "true"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_list_filter_by_is_dismissed(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        PaperRadarFactory(radar=radar)
        UserPaperActionFactory(user=user, paper=pr.paper, is_dismissed=True)
        response = client.get(PAPERS_URL, {"is_dismissed": "true"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_list_unauthenticated(self, api_client):
        response = api_client.get(PAPERS_URL)
        assert response.status_code == 401


@pytest.mark.django_db
class TestPaperDetail:
    def test_retrieve_own_paper(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        response = client.get(f"{PAPERS_URL}{pr.paper.id}/")
        assert response.status_code == 200
        assert response.data["pmid"] == pr.paper.pmid
        assert "abstract" in response.data

    def test_retrieve_paper_has_no_aisummary(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        response = client.get(f"{PAPERS_URL}{pr.paper.id}/")
        assert response.status_code == 200
        assert response.data["aisummary"] is None

    def test_retrieve_paper_with_aisummary(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        AISummaryFactory(paper=pr.paper, one_line_summary="Great finding.")
        response = client.get(f"{PAPERS_URL}{pr.paper.id}/")
        assert response.status_code == 200
        assert response.data["aisummary"]["one_line_summary"] == "Great finding."

    def test_retrieve_other_users_paper_returns_404(self, auth_client):
        client, _ = auth_client
        other_radar = RadarFactory(user=UserFactory())
        pr = PaperRadarFactory(radar=other_radar)
        response = client.get(f"{PAPERS_URL}{pr.paper.id}/")
        assert response.status_code == 404

    def test_retrieve_unauthenticated(self, api_client):
        paper = PaperFactory()
        response = api_client.get(f"{PAPERS_URL}{paper.id}/")
        assert response.status_code == 401


@pytest.mark.django_db
class TestUserPaperActions:
    def test_patch_creates_action_if_not_exists(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        response = client.patch(
            f"{PAPERS_URL}{pr.paper.id}/actions/", {"is_bookmarked": True}, format="json"
        )
        assert response.status_code == 200
        assert response.data["is_bookmarked"] is True

    def test_patch_bookmark(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        response = client.patch(
            f"{PAPERS_URL}{pr.paper.id}/actions/", {"is_bookmarked": True}, format="json"
        )
        assert response.data["is_bookmarked"] is True

    def test_patch_mark_read(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        response = client.patch(
            f"{PAPERS_URL}{pr.paper.id}/actions/", {"is_read": True}, format="json"
        )
        assert response.data["is_read"] is True

    def test_patch_dismiss(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        response = client.patch(
            f"{PAPERS_URL}{pr.paper.id}/actions/", {"is_dismissed": True}, format="json"
        )
        assert response.data["is_dismissed"] is True

    def test_patch_add_tags(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        response = client.patch(
            f"{PAPERS_URL}{pr.paper.id}/actions/",
            {"custom_tags_json": ["thesis", "key-paper"]},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["custom_tags_json"] == ["thesis", "key-paper"]

    def test_patch_notes(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        response = client.patch(
            f"{PAPERS_URL}{pr.paper.id}/actions/",
            {"notes_text": "Discuss with supervisor."},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["notes_text"] == "Discuss with supervisor."

    def test_patch_partial_leaves_other_fields(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        pr = PaperRadarFactory(radar=radar)
        UserPaperActionFactory(user=user, paper=pr.paper, is_bookmarked=True, is_read=False)
        response = client.patch(
            f"{PAPERS_URL}{pr.paper.id}/actions/", {"is_read": True}, format="json"
        )
        assert response.status_code == 200
        assert response.data["is_bookmarked"] is True
        assert response.data["is_read"] is True

    def test_patch_other_users_paper_returns_404(self, auth_client):
        client, _ = auth_client
        other_radar = RadarFactory(user=UserFactory())
        pr = PaperRadarFactory(radar=other_radar)
        response = client.patch(
            f"{PAPERS_URL}{pr.paper.id}/actions/", {"is_read": True}, format="json"
        )
        assert response.status_code == 404

    def test_patch_unauthenticated(self, api_client):
        paper = PaperFactory()
        response = api_client.patch(
            f"{PAPERS_URL}{paper.id}/actions/", {"is_read": True}, format="json"
        )
        assert response.status_code == 401
