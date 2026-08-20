from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_protocol import load_private_key, sign_command
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import DomainError
from app.dependencies.agent_identity import require_agent_identity
from app.models.operations import AgentCommand, RemoteAgent
from app.schemas.agent import (
    AgentCompletionRequest,
    AgentFailureRequest,
    AgentHeartbeatRequest,
    AgentProgressRequest,
    EnrollmentRequest,
)
from app.services.agent_command_service import AgentCommandService, canonical_json
from app.services.agent_enrollment_service import AgentEnrollmentService
from app.services.agent_health_service import AgentHealthService


router = APIRouter()


def _require_enabled() -> None:
    if not settings.AGENT_MODULE_ENABLED:
        raise DomainError(
            "AGENT_MODULE_DISABLED", "El módulo de agentes no está habilitado", 503
        )


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _command_response(command: AgentCommand) -> Response:
    body = canonical_json(
        {
            "id": str(command.id),
            "agentId": str(command.agent_id),
            "tenantId": str(command.tenant_id),
            "type": command.command_type,
            "payload": command.payload,
            "configRevision": int(command.payload.get("configRevision", 0)),
            "issuedAt": _isoformat(command.created_at),
            "expiresAt": _isoformat(command.expires_at),
            "idempotencyKey": command.idempotency_key,
        }
    )
    key_id = settings.AGENT_COMMAND_SIGNING_KEY_ID
    signature = sign_command(
        load_private_key(settings.AGENT_COMMAND_SIGNING_PRIVATE_KEY), key_id, body
    )
    return Response(
        body,
        media_type="application/json",
        headers={
            "X-Command-Key-Id": key_id,
            "X-Command-Signature": signature,
            "Cache-Control": "no-store",
        },
    )


def _command_ack(command: AgentCommand) -> dict[str, str]:
    return {"id": str(command.id), "status": command.status}


@router.post("/enroll", status_code=status.HTTP_201_CREATED)
async def enroll_agent(
    body: EnrollmentRequest,
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    agent = await AgentEnrollmentService(db).enroll(
        body.pairing_code,
        installation_id=str(body.installation_id),
        hostname=body.hostname,
        os_version=body.os_version,
        agent_version=body.agent_version,
        public_key=body.public_key,
        encryption_public_key=body.encryption_public_key,
    )
    await db.commit()
    return {
        "agentId": str(agent.id),
        "tenantId": str(agent.tenant_id),
        "commandSigningKeyId": settings.AGENT_COMMAND_SIGNING_KEY_ID,
        "minimumAgentVersion": settings.AGENT_MIN_VERSION,
        "pollIntervalSeconds": 25,
    }


@router.get("/commands/next")
async def next_command(
    wait: int = Query(25, ge=0, le=25),
    agent: RemoteAgent = Depends(require_agent_identity),
    db: AsyncSession = Depends(get_db),
):
    deadline = time.monotonic() + wait
    service = AgentCommandService(
        db, command_ttl_seconds=settings.AGENT_COMMAND_TTL_SEC
    )
    while True:
        command = await service.claim_next(agent)
        await db.commit()
        if command is not None:
            return _command_response(command)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        await asyncio.sleep(min(1.0, remaining))


@router.post("/commands/{command_id}/progress")
async def command_progress(
    command_id: str,
    body: AgentProgressRequest,
    agent: RemoteAgent = Depends(require_agent_identity),
    db: AsyncSession = Depends(get_db),
):
    command = await AgentCommandService(db).progress(
        agent,
        command_id,
        phase=body.phase,
        processed_units=body.processed_units,
        total_units=body.total_units,
        found_count=body.found_count,
        database=body.database,
        details=body.details,
    )
    await db.commit()
    return _command_ack(command)


@router.post("/commands/{command_id}/complete")
async def command_complete(
    command_id: str,
    body: AgentCompletionRequest,
    agent: RemoteAgent = Depends(require_agent_identity),
    db: AsyncSession = Depends(get_db),
):
    command = await AgentCommandService(db).complete(agent, command_id, body.result)
    await db.commit()
    return _command_ack(command)


@router.post("/commands/{command_id}/fail")
async def command_fail(
    command_id: str,
    body: AgentFailureRequest,
    agent: RemoteAgent = Depends(require_agent_identity),
    db: AsyncSession = Depends(get_db),
):
    command = await AgentCommandService(db).fail(
        agent, command_id, body.error_code, body.error_message
    )
    await db.commit()
    return _command_ack(command)


@router.post("/heartbeat")
async def heartbeat(
    body: AgentHeartbeatRequest,
    agent: RemoteAgent = Depends(require_agent_identity),
    db: AsyncSession = Depends(get_db),
):
    if body.agent_version:
        agent.agent_version = body.agent_version
    agent.metadata_json = body.metadata
    await AgentHealthService(db).record(
        agent=agent,
        health=body.health,
        volumes=body.volumes,
    )
    await db.commit()
    return {
        "status": "ok",
        "serverTime": datetime.now(timezone.utc).isoformat(),
        "minimumAgentVersion": settings.AGENT_MIN_VERSION,
    }
