from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.csrf import CSRFMiddleware


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.post("/api/v1/change")
    async def change():
        return {"changed": True}

    return TestClient(app)


def test_cookie_authenticated_mutation_requires_origin_and_csrf_header():
    client = _client()
    client.cookies.set("access_token", "signed-token")
    client.cookies.set("csrf_token", "csrf-value")

    missing = client.post("/api/v1/change", headers={"origin": settings.APP_ORIGIN})
    wrong_origin = client.post(
        "/api/v1/change",
        headers={"origin": "https://attacker.example", "x-csrf-token": "csrf-value"},
    )
    accepted = client.post(
        "/api/v1/change",
        headers={"origin": settings.APP_ORIGIN, "x-csrf-token": "csrf-value"},
    )

    assert missing.status_code == 403
    assert wrong_origin.status_code == 403
    assert accepted.status_code == 200
