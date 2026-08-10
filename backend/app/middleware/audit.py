import asyncio
import logging
import uuid

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings
from app.core.cookies import ACCESS_COOKIE
from app.core.database import AsyncSessionLocal
from app.models.audit_log import AuditLog

logger = logging.getLogger("audit")

AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if request.method in AUDIT_METHODS and request.url.path not in SKIP_PATHS:
            user_id, tenant_id = _extract_identity(request)
            asyncio.create_task(
                _write_audit(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    method=request.method,
                    path=request.url.path,
                    ip=request.client.host if request.client else None,
                    status_code=response.status_code,
                )
            )

        return response


def _extract_identity(request: Request) -> tuple[str | None, str | None]:
    token = request.cookies.get(ACCESS_COOKIE, "")
    if not token:
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            token = authorization[7:]
    if not token:
        return None, None
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload.get("sub"), payload.get("tenant_id")
    except Exception:
        return None, None


async def _write_audit(
    user_id: str | None,
    tenant_id: str | None,
    method: str,
    path: str,
    ip: str | None,
    status_code: int,
) -> None:
    try:
        async with AsyncSessionLocal() as db:
            log = AuditLog(
                user_id=uuid.UUID(user_id) if user_id else None,
                tenant_id=uuid.UUID(tenant_id) if tenant_id else None,
                method=method,
                path=path,
                ip_address=ip,
                status_code=status_code,
            )
            db.add(log)
            await db.commit()
    except Exception as exc:
        logger.warning("Audit write failed: %s", exc)
