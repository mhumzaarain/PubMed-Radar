import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.factories import UserFactory
from apps.radars.factories import RadarFactory
from apps.radars.models import Radar

RADARS_URL = "/api/radars/"


def make_auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


@pytest.mark.django_db
class TestRadarList:
    def test_list_empty(self, auth_client):
        client, _ = auth_client
        response = client.get(RADARS_URL)
        assert response.status_code == 200
        assert response.data["results"] == []

    def test_list_own_radars(self, auth_client):
        client, user = auth_client
        RadarFactory(user=user)
        RadarFactory(user=user)
        response = client.get(RADARS_URL)
        assert response.status_code == 200
        assert len(response.data["results"]) == 2

    def test_list_unauthenticated(self, api_client):
        response = api_client.get(RADARS_URL)
        assert response.status_code == 401

    def test_list_excludes_other_users_radars(self, auth_client):
        client, _ = auth_client
        other_user = UserFactory()
        RadarFactory(user=other_user)
        response = client.get(RADARS_URL)
        assert response.status_code == 200
        assert len(response.data["results"]) == 0


@pytest.mark.django_db
class TestRadarCreate:
    def test_create_success(self, auth_client):
        client, _ = auth_client
        payload = {"name": "Lung CT", "pubmed_query": "lung nodule AND CT", "schedule": "daily"}
        response = client.post(RADARS_URL, payload)
        assert response.status_code == 201
        assert response.data["name"] == "Lung CT"
        assert Radar.objects.count() == 1

    def test_create_missing_name(self, auth_client):
        client, _ = auth_client
        payload = {"pubmed_query": "lung nodule AND CT"}
        response = client.post(RADARS_URL, payload)
        assert response.status_code == 400

    def test_create_missing_query(self, auth_client):
        client, _ = auth_client
        payload = {"name": "Lung CT"}
        response = client.post(RADARS_URL, payload)
        assert response.status_code == 400

    def test_create_query_too_short(self, auth_client):
        client, _ = auth_client
        payload = {"name": "Lung CT", "pubmed_query": "ab"}
        response = client.post(RADARS_URL, payload)
        assert response.status_code == 400

    def test_create_empty_query(self, auth_client):
        client, _ = auth_client
        payload = {"name": "Lung CT", "pubmed_query": "   "}
        response = client.post(RADARS_URL, payload)
        assert response.status_code == 400

    def test_create_invalid_schedule(self, auth_client):
        client, _ = auth_client
        payload = {"name": "Lung CT", "pubmed_query": "lung nodule", "schedule": "hourly"}
        response = client.post(RADARS_URL, payload)
        assert response.status_code == 400

    def test_create_unauthenticated(self, api_client):
        payload = {"name": "Lung CT", "pubmed_query": "lung nodule AND CT"}
        response = api_client.post(RADARS_URL, payload)
        assert response.status_code == 401


@pytest.mark.django_db
class TestRadarDetail:
    def test_retrieve_own_radar(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        response = client.get(f"{RADARS_URL}{radar.id}/")
        assert response.status_code == 200
        assert str(response.data["id"]) == str(radar.id)

    def test_retrieve_other_users_radar_returns_404(self, auth_client):
        client, _ = auth_client
        other_radar = RadarFactory(user=UserFactory())
        response = client.get(f"{RADARS_URL}{other_radar.id}/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestRadarUpdate:
    def test_partial_update(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user, name="Old Name")
        response = client.patch(f"{RADARS_URL}{radar.id}/", {"name": "New Name"})
        assert response.status_code == 200
        assert response.data["name"] == "New Name"

    def test_update_other_users_radar_returns_404(self, auth_client):
        client, _ = auth_client
        other_radar = RadarFactory(user=UserFactory())
        response = client.patch(f"{RADARS_URL}{other_radar.id}/", {"name": "Hacked"})
        assert response.status_code == 404


@pytest.mark.django_db
class TestRadarDelete:
    def test_delete_own_radar(self, auth_client):
        client, user = auth_client
        radar = RadarFactory(user=user)
        response = client.delete(f"{RADARS_URL}{radar.id}/")
        assert response.status_code == 204
        assert Radar.objects.count() == 0

    def test_delete_other_users_radar_returns_404(self, auth_client):
        client, _ = auth_client
        other_radar = RadarFactory(user=UserFactory())
        response = client.delete(f"{RADARS_URL}{other_radar.id}/")
        assert response.status_code == 404
        assert Radar.objects.count() == 1
