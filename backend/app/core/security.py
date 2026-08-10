import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.session_store import SessionStore, get_session_store

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _encode(payload: dict) -> str:
    payload = {**payload}
    payload.setdefault("jti", str(uuid.uuid4()))
    payload.setdefault("iat", datetime.now(timezone.utc))
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(
    subject: Any,
    expires_delta: timedelta | None = None,
    *,
    tenant_id: str | None = None,
    sid: str | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return _encode({"sub": str(subject), "tenant_id": tenant_id, "sid": sid, "exp": expire, "type": "access"})


def create_refresh_token(
    subject: Any,
    *,
    tenant_id: str | None = None,
    sid: str | None = None,
    jti: str | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(subject), "tenant_id": tenant_id, "sid": sid, "exp": expire, "type": "refresh"}
    if jti:
        payload["jti"] = jti
    return _encode(payload)



def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    return payload


async def get_request_token(
    request: Request,
    bearer_token: str | None = Depends(oauth2_scheme),
) -> str:
    token = request.cookies.get("access_token") or bearer_token
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesi?n no autenticada")
    return token


async def get_current_user(
    token: str = Depends(get_request_token),
    db: AsyncSession = Depends(get_db),
    sessions: SessionStore = Depends(get_session_store),
):
    from app.models.user import User  # local import avoids circular

    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tipo de token inválido")

    try:
        subject = uuid.UUID(str(payload.get("sub", "")))
        tenant_id = uuid.UUID(str(payload.get("tenant_id", "")))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identidad de sesión inválida",
        ) from exc
    if not payload.get("sid") or not await sessions.validate(
        payload["sid"], str(subject)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesion expirada"
        )
    result = await db.execute(
        select(User).where(User.id == subject, User.tenant_id == tenant_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta desactivada")
    return user


async def get_current_user_id(current_user=Depends(get_current_user)) -> str:
    """Dependency que devuelve solo el id del usuario autenticado (como string).
    Usado por los routers que no necesitan el objeto User completo."""
    return str(current_user.id)


def require_roles(*roles):
    """Dependency factory for role-based access control."""
    async def checker(current_user=Depends(get_current_user)):
        from app.models.user import UserRole
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere uno de los roles: {', '.join(r.value for r in roles)}",
            )
        return current_user
    return checker
