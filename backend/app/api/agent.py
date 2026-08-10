from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import DomainError
from app.schemas.agent import EnrollmentRequest
from app.services.agent_enrollment_service import AgentEnrollmentService


router = APIRouter()


@router.post("/enroll", status_code=status.HTTP_201_CREATED)
async def enroll_agent(
    body: EnrollmentRequest,
    db: AsyncSession = Depends(get_db),
):
    if not settings.AGENT_MODULE_ENABLED:
        raise DomainError(
            "AGENT_MODULE_DISABLED", "El módulo de agentes no está habilitado", 503
        )
    agent = await AgentEnrollmentService(db).enroll(
        body.pairing_code,
        installation_id=str(body.installation_id),
        hostname=body.hostname,
        os_version=body.os_version,
        agent_version=body.agent_version,
        public_key=body.public_key,
    )
    await db.commit()
    return {
        "agentId": str(agent.id),
        "tenantId": str(agent.tenant_id),
        "commandSigningKeyId": settings.AGENT_COMMAND_SIGNING_KEY_ID,
        "minimumAgentVersion": settings.AGENT_MIN_VERSION,
        "pollIntervalSeconds": 25,
    }

