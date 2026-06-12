import pytest
from procrastinate import testing
from procrastinate.contrib.django import procrastinate_app
from rest_framework.test import APIClient

from apps.users.factories import UserFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.fixture
def procrastinate_in_memory():
    """Procrastinate app backed by an in-memory connector.

    Deferred jobs are visible via `procrastinate_in_memory.connector.jobs`
    (dict of job-id -> job dict) instead of hitting the database.
    """
    in_memory = testing.InMemoryConnector()
    with procrastinate_app.current_app.replace_connector(in_memory) as app:
        yield app
