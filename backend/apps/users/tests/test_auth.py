import pytest

from apps.users.factories import UserFactory

REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"
RADARS_URL = "/api/radars/"


@pytest.mark.django_db
class TestRegister:
    def test_register_success(self, api_client):
        payload = {"email": "new@example.com", "password": "strongpass1"}
        response = api_client.post(REGISTER_URL, payload)
        assert response.status_code == 201
        assert "access" in response.data
        assert "refresh" in response.data

    def test_register_duplicate_email(self, api_client):
        UserFactory(email="taken@example.com")
        payload = {"email": "taken@example.com", "password": "strongpass1"}
        response = api_client.post(REGISTER_URL, payload)
        assert response.status_code == 400

    def test_register_invalid_email(self, api_client):
        payload = {"email": "not-an-email", "password": "strongpass1"}
        response = api_client.post(REGISTER_URL, payload)
        assert response.status_code == 400

    def test_register_password_too_short(self, api_client):
        payload = {"email": "new@example.com", "password": "short"}
        response = api_client.post(REGISTER_URL, payload)
        assert response.status_code == 400


@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client):
        UserFactory(email="user@example.com")
        # UserFactory sets password via set_password("testpass123")
        payload = {"email": "user@example.com", "password": "testpass123"}
        response = api_client.post(LOGIN_URL, payload)
        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data

    def test_login_wrong_password(self, api_client):
        UserFactory(email="user@example.com")
        payload = {"email": "user@example.com", "password": "wrongpass"}
        response = api_client.post(LOGIN_URL, payload)
        assert response.status_code == 401

    def test_login_nonexistent_user(self, api_client):
        payload = {"email": "nobody@example.com", "password": "anypass123"}
        response = api_client.post(LOGIN_URL, payload)
        assert response.status_code == 401


@pytest.mark.django_db
class TestProtectedEndpoints:
    def test_requires_auth(self, api_client):
        response = api_client.get(RADARS_URL)
        assert response.status_code == 401

    def test_accessible_with_token(self, auth_client):
        client, _ = auth_client
        response = client.get(RADARS_URL)
        assert response.status_code == 200
