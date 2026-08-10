from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import Capability, require_capabilities
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import DomainError
from app.models.operations import RemoteAgent
from app.models.user import User
from app.services.agent_enrollment_service import AgentEnrollmentService


router = APIRouter()
manage_config = require_capabilities(Capability.CONFIG_MANAGE)


def _require_enabled() -> None:
    if not settings.AGENT_MODULE_ENABLED:
        raise DomainError(
            "AGENT_MODULE_DISABLED", "El módulo de agentes no está habilitado", 503
        )


def _serialize(agent: RemoteAgent) -> dict:
    return {
        "id": str(agent.id),
        "hostname": agent.hostname,
        "osVersion": agent.os_version,
        "agentVersion": agent.agent_version,
        "status": agent.status,
        "lastSeenAt": agent.last_seen_at.isoformat() if agent.last_seen_at else None,
        "revokedAt": agent.revoked_at.isoformat() if agent.revoked_at else None,
        "createdAt": agent.created_at.isoformat() if agent.created_at else None,
    }


@router.get("")
async def list_agents(
    current_user: User = Depends(manage_config),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    items = await AgentEnrollmentService(db).list_agents(str(current_user.tenant_id))
    return {"items": [_serialize(item) for item in items], "total": len(items)}


@router.post("/pairing-codes", status_code=status.HTTP_201_CREATED)
async def create_pairing_code(
    current_user: User = Depends(manage_config),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    result = await AgentEnrollmentService(
        db, enrollment_ttl_seconds=settings.AGENT_ENROLLMENT_TTL_SEC
    ).issue_pairing_code(str(current_user.tenant_id), str(current_user.id))
    await db.commit()
    return result


@router.post("/{agent_id}/replace", status_code=status.HTTP_201_CREATED)
async def replace_agent(
    agent_id: str,
    current_user: User = Depends(manage_config),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    result = await AgentEnrollmentService(
        db, enrollment_ttl_seconds=settings.AGENT_ENROLLMENT_TTL_SEC
    ).issue_pairing_code(
        str(current_user.tenant_id), str(current_user.id), agent_id
    )
    await db.commit()
    return result


@router.post("/{agent_id}/revoke")
async def revoke_agent(
    agent_id: str,
    current_user: User = Depends(manage_config),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    agent = await AgentEnrollmentService(db).revoke(
        str(current_user.tenant_id), agent_id
    )
    await db.commit()
    return _serialize(agent)

