import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.users.factories import UserFactory

User = get_user_model()

LOGIN_URL = "/login/"
LOGOUT_URL = "/logout/"
DASHBOARD_URL = "/"
REGISTER_URL = "/register/"


@pytest.mark.django_db
class TestLoginPage:
    def test_login_page_renders(self, client):
        response = client.get(LOGIN_URL)
        assert response.status_code == 200
        assert b"<form" in response.content

    def test_login_success_redirects_to_dashboard(self, client):
        user = UserFactory()
        response = client.post(
            LOGIN_URL, {"username": user.email, "password": "testpass123"}
        )
        assert response.status_code == 302
        assert response.url == DASHBOARD_URL

    def test_login_wrong_password_shows_error(self, client):
        user = UserFactory()
        response = client.post(LOGIN_URL, {"username": user.email, "password": "nope"})
        assert response.status_code == 200
        assert response.context["form"].errors

    def test_authenticated_user_redirected_away_from_login(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(LOGIN_URL)
        assert response.status_code == 302
        assert response.url == DASHBOARD_URL


@pytest.mark.django_db
class TestLogout:
    def test_logout_post_redirects_to_login(self, client):
        client.force_login(UserFactory())
        response = client.post(LOGOUT_URL)
        assert response.status_code == 302
        assert response.url == LOGIN_URL

    def test_logout_get_not_allowed(self, client):
        client.force_login(UserFactory())
        response = client.get(LOGOUT_URL)
        assert response.status_code == 405


@pytest.mark.django_db
class TestRegisterPage:
    def test_register_page_renders(self, client):
        response = client.get(REGISTER_URL)
        assert response.status_code == 200
        assert b"<form" in response.content

    def test_register_creates_user_logs_in_and_redirects(self, client):
        payload = {
            "email": "new@example.com",
            "password": "phase2-Secur3-pw",
            "password_confirm": "phase2-Secur3-pw",
        }
        response = client.post(REGISTER_URL, payload)
        assert response.status_code == 302
        assert response.url == DASHBOARD_URL
        assert User.objects.filter(email="new@example.com").exists()
        # auto-login: dashboard now renders instead of redirecting
        assert client.get(DASHBOARD_URL).status_code == 200

    def test_register_duplicate_email_shows_error(self, client):
        UserFactory(email="taken@example.com")
        payload = {
            "email": "taken@example.com",
            "password": "phase2-Secur3-pw",
            "password_confirm": "phase2-Secur3-pw",
        }
        response = client.post(REGISTER_URL, payload)
        assert response.status_code == 200
        assert "email" in response.context["form"].errors

    def test_register_password_mismatch_shows_error(self, client):
        payload = {
            "email": "new@example.com",
            "password": "phase2-Secur3-pw",
            "password_confirm": "different-pw-123",
        }
        response = client.post(REGISTER_URL, payload)
        assert response.status_code == 200
        assert "password_confirm" in response.context["form"].errors

    def test_register_weak_password_shows_error(self, client):
        payload = {
            "email": "new@example.com",
            "password": "12345678",
            "password_confirm": "12345678",
        }
        response = client.post(REGISTER_URL, payload)
        assert response.status_code == 200
        assert "password" in response.context["form"].errors

    def test_register_mixed_case_email_can_log_back_in(self, client):
        payload = {
            "email": "Foo@Example.COM",
            "password": "phase2-Secur3-pw",
            "password_confirm": "phase2-Secur3-pw",
        }
        client.post(REGISTER_URL, payload)
        client.post(LOGOUT_URL)
        response = client.post(
            LOGIN_URL, {"username": "Foo@Example.COM", "password": "phase2-Secur3-pw"}
        )
        assert response.status_code == 302
        assert response.url == DASHBOARD_URL

    def test_register_password_similar_to_email_rejected(self, client):
        payload = {
            "email": "carolyn.fischer@example.com",
            "password": "carolyn.fischer",
            "password_confirm": "carolyn.fischer",
        }
        response = client.post(REGISTER_URL, payload)
        assert response.status_code == 200
        assert "password" in response.context["form"].errors


@pytest.mark.django_db
class TestDashboardShell:
    def test_anonymous_redirected_to_login(self, client):
        response = client.get(DASHBOARD_URL)
        assert response.status_code == 302
        assert response.url == f"{LOGIN_URL}?next=/"

    def test_renders_for_logged_in_user(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(DASHBOARD_URL)
        assert response.status_code == 200
        assert b'id="radar-list"' in response.content
        assert user.email.encode() in response.content


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestAuthThrottling:
    def test_login_throttled_after_20_posts(self, client):
        user = UserFactory()
        for _ in range(20):
            response = client.post(
                LOGIN_URL, {"username": user.email, "password": "wrong"}
            )
            assert response.status_code == 200
        response = client.post(
            LOGIN_URL, {"username": user.email, "password": "wrong"}
        )
        assert response.status_code == 429

    def test_register_throttled_after_10_posts(self, client):
        for i in range(10):
            response = client.post(
                REGISTER_URL,
                {
                    "email": f"u{i}@example.com",
                    "password": "phase2-Secur3-pw",
                    "password_confirm": "phase2-Secur3-pw",
                },
            )
            assert response.status_code == 302
        response = client.post(
            REGISTER_URL,
            {
                "email": "u11@example.com",
                "password": "phase2-Secur3-pw",
                "password_confirm": "phase2-Secur3-pw",
            },
        )
        assert response.status_code == 429

    def test_get_requests_not_throttled(self, client):
        for _ in range(25):
            assert client.get(LOGIN_URL).status_code == 200
