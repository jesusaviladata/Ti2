from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import Base
from app.services.session_store import SessionStore


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Transaction:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, _exc, _tb):
        self.db.transaction_committed = exc_type is None


class _Database:
    def __init__(self, results=None, error=None):
        self.results = list(results or [])
        self.error = error
        self.added = []
        self.transaction_committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _tb):
        return None

    def begin(self):
        return _Transaction(self)

    def add(self, value):
        self.added.append(value)

    async def execute(self, _statement):
        if self.error:
            raise self.error
        return _Result(self.results.pop(0) if self.results else None)


def _factory(db):
    return lambda: db


def test_auth_session_tables_are_registered():
    import app.models  # noqa: F401

    assert "auth_sessions" in Base.metadata.tables
    assert "auth_refresh_history" in Base.metadata.tables
    assert "auth_login_limits" in Base.metadata.tables


@pytest.mark.asyncio
async def test_reused_refresh_is_committed_as_a_revoked_session_before_401():
    row = SimpleNamespace(
        sid=uuid.uuid4(),
        current_refresh_jti=uuid.uuid4(),
        csrf_token="csrf",
        revoked_at=None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db = _Database(results=[row])
    store = SessionStore(_factory(db))

    with pytest.raises(HTTPException) as rejected:
        await store.rotate(str(row.sid), str(uuid.uuid4()))

    assert rejected.value.status_code == 401
    assert row.revoked_at is not None
    assert db.transaction_committed is True


@pytest.mark.asyncio
async def test_database_failure_becomes_controlled_503():
    db = _Database(error=SQLAlchemyError("connection details must stay private"))
    store = SessionStore(_factory(db))

    with pytest.raises(HTTPException) as unavailable:
        await store.validate(str(uuid.uuid4()), str(uuid.uuid4()))

    assert unavailable.value.status_code == 503
    assert "connection details" not in str(unavailable.value.detail)


def test_rate_limit_key_is_opaque():
    raw = "admin@dataexpress.example:10.0.0.8"

    hashed = SessionStore.rate_key(raw)

    assert raw not in hashed
    assert len(hashed) == 64
