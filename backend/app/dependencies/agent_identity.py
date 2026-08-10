from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import DomainError
from app.models.operations import RemoteAgent
from app.services.agent_auth_service import AgentAuthService


def _request_target(request: Request) -> str:
    raw_path = request.scope.get("raw_path", request.url.path.encode("ascii"))
    query = request.scope.get("query_string", b"")
    try:
        target = raw_path.decode("ascii")
        if query:
            target += "?" + query.decode("ascii")
        return target
    except UnicodeDecodeError:
        raise DomainError(
            "AGENT_REQUEST_INVALID", "La solicitud del agente no es válida", 400
        ) from None


async def require_agent_identity(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RemoteAgent:
    if not settings.AGENT_MODULE_ENABLED:
        raise DomainError(
            "AGENT_MODULE_DISABLED", "El módulo de agentes no está habilitado", 503
        )
    body = await request.body()
    if len(body) > settings.AGENT_MAX_BODY_BYTES:
        raise DomainError(
            "AGENT_BODY_TOO_LARGE", "La solicitud del agente es demasiado grande", 413
        )
    return await AgentAuthService(
        db,
        max_clock_skew=settings.AGENT_MAX_CLOCK_SKEW_SEC,
    ).authenticate(
        agent_id=request.headers.get("X-Agent-Id", ""),
        timestamp=request.headers.get("X-Agent-Timestamp", ""),
        nonce=request.headers.get("X-Agent-Nonce", ""),
        signature=request.headers.get("X-Agent-Signature", ""),
        method=request.method,
        path_with_query=_request_target(request),
        body=body,
    )

