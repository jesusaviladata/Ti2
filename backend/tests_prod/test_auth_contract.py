import uuid
from types import SimpleNamespace

import pytest
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


def _client_for(user) -> TestClient:
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth")

    async def _override_db():
        yield _FakeSession(user)

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app, raise_server_exceptions=False)


def _active_user():
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


def test_unknown_email_is_a_controlled_401_not_an_internal_error():
    client = _client_for(None)

    response = client.post(
        "/api/v1/auth/login",
        data={"username": "missing@dataexpress.local", "password": "wrong"},
    )

    assert response.status_code == 401


def test_successful_login_sets_http_only_session_cookies_without_returning_tokens():
    client = _client_for(_active_user())

    response = client.post(
        "/api/v1/auth/login",
        data={"username": "admin@dataexpress.local", "password": "CorrectHorse123!"},
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}
    assert response.cookies.get("access_token")
    assert response.cookies.get("refresh_token")
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "access_token" not in response.json()
    assert "refresh_token" not in response.json()

