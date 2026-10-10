"""Health route against the test Postgres (as the app role) and the real Redis."""

from fastapi.testclient import TestClient

from staffroom_api.main import create_app
from staffroom_api.settings import Settings


def test_health_ok_when_dependencies_are_up(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": "ok", "redis": "ok"}}


def test_health_503_when_redis_is_down(api_settings: Settings) -> None:
    settings = api_settings.model_copy(update={"redis_port": 1})  # nothing listens there
    with TestClient(create_app(settings)) as client:  # `with` runs the lifespan
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["checks"] == {"postgres": "ok", "redis": "error"}
