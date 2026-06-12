import pytest
from django.test import Client

from apps.users.factories import UserFactory

RADARS_URL = "/api/radars/"


@pytest.mark.django_db
class TestSessionApiAccess:
    def test_session_login_grants_api_access(self, client):
        client.force_login(UserFactory())
        response = client.get(RADARS_URL)
        assert response.status_code == 200

    def test_unauthenticated_api_request_rejected(self, client):
        response = client.get(RADARS_URL)
        assert response.status_code == 403

    def test_unsafe_method_without_csrf_token_rejected(self):
        # The contract js/api.js is written against: session-authed unsafe
        # requests MUST carry X-CSRFToken, or DRF's SessionAuthentication 403s.
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(UserFactory())
        response = csrf_client.post(
            RADARS_URL, {"name": "x", "pubmed_query": "cancer imaging"}
        )
        assert response.status_code == 403
