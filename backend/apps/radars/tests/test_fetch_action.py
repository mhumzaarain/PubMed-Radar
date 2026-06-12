import pytest

from apps.radars.factories import RadarFactory
from apps.users.factories import UserFactory

RADARS_URL = "/api/radars/"
FETCH_TASK = "apps.radars.tasks.fetch_radar_task"


def _fetch_jobs(app):
    return [j for j in app.connector.jobs.values() if j["task_name"] == FETCH_TASK]


@pytest.mark.django_db
class TestFetchAction:
    def test_fetch_returns_202_and_queues_job(self, auth_client, procrastinate_in_memory):
        client, user = auth_client
        radar = RadarFactory(user=user)
        response = client.post(f"{RADARS_URL}{radar.id}/fetch/")
        assert response.status_code == 202
        assert response.data == {"status": "queued"}
        jobs = _fetch_jobs(procrastinate_in_memory)
        assert len(jobs) == 1
        assert jobs[0]["args"] == {"radar_id": str(radar.id)}

    def test_duplicate_fetch_still_202_but_queued_once(self, auth_client, procrastinate_in_memory):
        client, user = auth_client
        radar = RadarFactory(user=user)
        client.post(f"{RADARS_URL}{radar.id}/fetch/")
        response = client.post(f"{RADARS_URL}{radar.id}/fetch/")
        assert response.status_code == 202
        assert len(_fetch_jobs(procrastinate_in_memory)) == 1

    def test_fetch_other_users_radar_returns_404(self, auth_client):
        client, _ = auth_client
        other_radar = RadarFactory(user=UserFactory())
        response = client.post(f"{RADARS_URL}{other_radar.id}/fetch/")
        assert response.status_code == 404

    def test_fetch_unauthenticated(self, api_client):
        radar = RadarFactory()
        response = api_client.post(f"{RADARS_URL}{radar.id}/fetch/")
        assert response.status_code == 403
