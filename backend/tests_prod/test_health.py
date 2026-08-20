from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import health


def test_readiness_tracks_latest_database_migration():
    assert health.EXPECTED_ALEMBIC_REVISION == "0009"


def _client(readiness):
    app = FastAPI()
    app.include_router(health.router)
    app.dependency_overrides[health.get_readiness] = lambda: readiness
    return TestClient(app)


def test_liveness_does_not_depend_on_database():
    response = _client({"ready": False, "reason": "database_unavailable"}).get(
        "/health/live"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_readiness_returns_503_when_database_is_not_ready():
    response = _client({"ready": False, "reason": "migration_outdated"}).get(
        "/health/ready"
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "SERVICE_NOT_READY",
        "reason": "migration_outdated",
    }


def test_readiness_returns_revision_when_ready():
    response = _client({"ready": True, "revision": "0002"}).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "revision": "0002"}
