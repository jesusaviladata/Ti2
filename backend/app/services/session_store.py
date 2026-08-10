import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.auth_session import AuthLoginLimit, AuthRefreshHistory, AuthSession


@dataclass(frozen=True)
class SessionData:
    sid: str
    refresh_jti: str
    csrf_token: str


class SessionStore:
    def __init__(self, session_factory: Any):
        self.session_factory = session_factory
        self.session_ttl = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        self.login_window = timedelta(seconds=settings.LOGIN_FAIL_WINDOW_SEC)

    @staticmethod
    def rate_key(raw_key: str) -> str:
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            raw_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def create(self, user_id: str, tenant_id: str) -> SessionData:
        now = _utcnow()
        data = SessionData(str(uuid.uuid4()), str(uuid.uuid4()), secrets.token_urlsafe(32))
        try:
            async with self.session_factory() as db:
                async with db.begin():
                    db.add(
                        AuthSession(
                            sid=uuid.UUID(data.sid),
                            user_id=uuid.UUID(user_id),
                            tenant_id=uuid.UUID(tenant_id),
                            current_refresh_jti=uuid.UUID(data.refresh_jti),
                            csrf_token=data.csrf_token,
                            expires_at=now + self.session_ttl,
                        )
                    )
        except (SQLAlchemyError, ValueError) as exc:
            raise _unavailable() from exc
        return data

    async def validate(self, sid: str, user_id: str) -> bool:
        try:
            sid_value = uuid.UUID(sid)
            user_value = uuid.UUID(user_id)
        except ValueError:
            return False
        try:
            async with self.session_factory() as db:
                result = await db.execute(
                    select(AuthSession).where(
                        AuthSession.sid == sid_value,
                        AuthSession.user_id == user_value,
                    )
                )
                row = result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise _unavailable() from exc
        return bool(row and row.revoked_at is None and row.expires_at > _utcnow())

    async def rotate(self, sid: str, presented_jti: str) -> tuple[str, str]:
        try:
            sid_value = uuid.UUID(sid)
            presented_value = uuid.UUID(presented_jti)
        except ValueError as exc:
            raise _expired() from exc

        new_jti = uuid.uuid4()
        outcome: tuple[str, str] | None = None
        rejected = False
        now = _utcnow()
        try:
            async with self.session_factory() as db:
                async with db.begin():
                    result = await db.execute(
                        select(AuthSession)
                        .where(AuthSession.sid == sid_value)
                        .with_for_update()
                    )
                    row = result.scalar_one_or_none()
                    if row is None or row.revoked_at is not None or row.expires_at <= now:
                        rejected = True
                    elif row.current_refresh_jti != presented_value:
                        row.revoked_at = now
                        rejected = True
                    else:
                        db.add(
                            AuthRefreshHistory(
                                sid=row.sid,
                                refresh_jti=row.current_refresh_jti,
                                consumed_at=now,
                            )
                        )
                        row.current_refresh_jti = new_jti
                        row.updated_at = now
                        outcome = (str(new_jti), row.csrf_token)
        except SQLAlchemyError as exc:
            raise _unavailable() from exc

        if rejected or outcome is None:
            raise _expired()
        return outcome

    async def revoke(self, sid: str) -> None:
        try:
            sid_value = uuid.UUID(sid)
        except ValueError:
            return
        try:
            async with self.session_factory() as db:
                async with db.begin():
                    result = await db.execute(
                        select(AuthSession)
                        .where(AuthSession.sid == sid_value)
                        .with_for_update()
                    )
                    row = result.scalar_one_or_none()
                    if row is not None and row.revoked_at is None:
                        row.revoked_at = _utcnow()
        except SQLAlchemyError as exc:
            raise _unavailable() from exc

    async def revoke_user(self, user_id: str) -> None:
        try:
            user_value = uuid.UUID(user_id)
        except ValueError:
            return
        try:
            async with self.session_factory() as db:
                async with db.begin():
                    result = await db.execute(
                        select(AuthSession)
                        .where(
                            AuthSession.user_id == user_value,
                            AuthSession.revoked_at.is_(None),
                        )
                        .with_for_update()
                    )
                    for row in result.scalars().all():
                        row.revoked_at = _utcnow()
        except SQLAlchemyError as exc:
            raise _unavailable() from exc

    async def login_failures(self, key: str) -> int:
        key_hash = self.rate_key(key)
        now = _utcnow()
        try:
            async with self.session_factory() as db:
                async with db.begin():
                    result = await db.execute(
                        select(AuthLoginLimit)
                        .where(AuthLoginLimit.key_hash == key_hash)
                        .with_for_update()
                    )
                    row = result.scalar_one_or_none()
                    if row is None:
                        return 0
                    if row.expires_at <= now:
                        await db.delete(row)
                        return 0
                    return row.attempts
        except SQLAlchemyError as exc:
            raise _unavailable() from exc

    async def record_login_failure(self, key: str) -> None:
        key_hash = self.rate_key(key)
        now = _utcnow()
        try:
            async with self.session_factory() as db:
                async with db.begin():
                    result = await db.execute(
                        select(AuthLoginLimit)
                        .where(AuthLoginLimit.key_hash == key_hash)
                        .with_for_update()
                    )
                    row = result.scalar_one_or_none()
                    if row is None:
                        db.add(
                            AuthLoginLimit(
                                key_hash=key_hash,
                                attempts=1,
                                expires_at=now + self.login_window,
                            )
                        )
                    elif row.expires_at <= now:
                        row.attempts = 1
                        row.expires_at = now + self.login_window
                        row.updated_at = now
                    else:
                        row.attempts += 1
                        row.updated_at = now
        except SQLAlchemyError as exc:
            raise _unavailable() from exc

    async def clear_login_failures(self, key: str) -> None:
        try:
            async with self.session_factory() as db:
                async with db.begin():
                    await db.execute(
                        delete(AuthLoginLimit).where(
                            AuthLoginLimit.key_hash == self.rate_key(key)
                        )
                    )
        except SQLAlchemyError as exc:
            raise _unavailable() from exc


_session_store = SessionStore(AsyncSessionLocal)


def get_session_store() -> SessionStore:
    return _session_store


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _expired() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesion expirada o reutilizada",
    )


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Servicio de autenticacion temporalmente no disponible",
    )
