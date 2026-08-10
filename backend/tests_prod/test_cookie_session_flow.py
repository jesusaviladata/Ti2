import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import auth
from app.core.database import get_db
from app.core.security import hash_password
from app.models.user import UserRole


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, user):
        self.user = user

    async def execute(self, _statement):
        return _ScalarResult(self.user)

    async def commit(self):
        return None


def _user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@dataexpress.local",
        username="admin",
        full_name="Administrador Data Express",
        role=UserRole.admin,
        is_active=True,
        totp_enabled=False,
        totp_secret=None,
        hashed_password=hash_password("CorrectHorse123!"),
    )


def _authenticated_client() -> TestClient:
    user = _user()
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth")

    async def _override_db():
        yield _FakeSession(user)

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/auth/login",
        data={"username": user.email, "password": "CorrectHorse123!"},
    )
    assert response.status_code == 200
    return client


def test_me_accepts_the_http_only_access_cookie():
    client = _authenticated_client()

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "admin@dataexpress.local"


def test_refresh_uses_cookie_without_request_body_and_never_returns_tokens():
    client = _authenticated_client()
    previous_refresh = client.cookies.get("refresh_token")

    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 204
    assert response.content == b""
    assert client.cookies.get("access_token")
    assert client.cookies.get("refresh_token")
    assert client.cookies.get("refresh_token") != previous_refresh


def test_logout_is_idempotent_and_clears_all_auth_cookies():
    client = _authenticated_client()

    first = client.post("/api/v1/auth/logout")
    second = client.post("/api/v1/auth/logout")

    assert first.status_code == 204
    assert second.status_code == 204
    assert client.cookies.get("access_token") is None
    assert client.cookies.get("refresh_token") is None

