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


def test_login_ignores_legacy_totp_columns_and_no_totp_routes_exist():
    user = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="operador@dataexpress.local",
        username="operador",
        full_name="Operador Data Express",
        role=UserRole.technician,
        is_active=True,
        totp_enabled=True,
        totp_secret="legacy-secret",
        hashed_password=hash_password("CorrectHorse123!"),
    )
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth")

    async def _override_db():
        yield _FakeSession(user)

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app, raise_server_exceptions=False)

    login = client.post(
        "/api/v1/auth/login",
        data={"username": user.email, "password": "CorrectHorse123!"},
    )

    assert login.status_code == 200
    assert login.json() == {"authenticated": True}
    assert client.cookies.get("preauth_token") is None
    assert client.cookies.get("access_token")
    assert client.post("/api/v1/auth/totp/verify", json={"code": "000000"}).status_code == 404