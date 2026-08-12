from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import Capability, require_capabilities
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import DomainError
from app.models.operations import RemoteAgent
from app.models.user import User
from app.services.agent_admin_service import (
    DEFAULT_TARGET_FILES,
    DEFAULT_TARGET_FOLDERS,
    AgentAdminService,
    server_payload,
)
from app.services.agent_enrollment_service import AgentEnrollmentService


router = APIRouter()
manage_config = require_capabilities(Capability.CONFIG_MANAGE)
read_operation = require_capabilities(Capability.OPERATION_READ)
simulate_cleanup = require_capabilities(Capability.CLEANUP_SIMULATE)
execute_cleanup = require_capabilities(Capability.CLEANUP_EXECUTE)
purge_cleanup = require_capabilities(Capability.PURGE)


class BrowseRequest(BaseModel):
    path: str | None = Field(None, max_length=2048)

    model_config = {"extra": "forbid"}


class ValidateRequest(BaseModel):
    root: str = Field(min_length=3, max_length=2048)
    target_folders: list[str] = Field(
        default_factory=lambda: list(DEFAULT_TARGET_FOLDERS), alias="targetFolders", max_length=20
    )
    target_files: list[str] = Field(
        default_factory=lambda: list(DEFAULT_TARGET_FILES), alias="targetFiles", max_length=20
    )

    model_config = {"populate_by_name": True, "extra": "forbid"}


class ConfigurationRequest(ValidateRequest):
    name: str = Field(min_length=1, max_length=255)
    validation_job_id: str = Field(alias="validationJobId")
    server_id: str | None = Field(None, alias="serverId")


class CleanupSimulationRequest(BaseModel):
    server_id: str = Field(alias="serverId")
    container_folder: str = Field("Core", alias="containerFolder", min_length=1, max_length=64)
    max_properties: int = Field(0, alias="maxProperties", ge=0, le=10000)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class CleanupExecutionRequest(BaseModel):
    simulation_id: str = Field(alias="simulationId")
    manifest_hash: str = Field(alias="manifestHash", min_length=64, max_length=64)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class QuarantineActionRequest(BaseModel):
    server_id: str = Field(alias="serverId")
    execution_id: str = Field(alias="executionId")
    relative_path: str | None = Field(None, alias="relativePath", max_length=2048)

    model_config = {"populate_by_name": True, "extra": "forbid"}


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


@router.post("/{agent_id}/browse", status_code=status.HTTP_202_ACCEPTED)
async def browse_agent(
    agent_id: str,
    body: BrowseRequest,
    current_user: User = Depends(manage_config),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    job = await AgentAdminService(db).start_browse(
        str(current_user.tenant_id), agent_id, body.path
    )
    await db.commit()
    return {"jobId": str(job.id)}


@router.post("/{agent_id}/validate", status_code=status.HTTP_202_ACCEPTED)
async def validate_agent_structure(
    agent_id: str,
    body: ValidateRequest,
    current_user: User = Depends(manage_config),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    job = await AgentAdminService(db).start_validation(
        str(current_user.tenant_id),
        agent_id,
        root=body.root,
        target_folders=body.target_folders,
        target_files=body.target_files,
    )
    await db.commit()
    return {"jobId": str(job.id)}


@router.post("/{agent_id}/cleanup/simulate", status_code=status.HTTP_202_ACCEPTED)
async def simulate_agent_cleanup(
    agent_id: str,
    body: CleanupSimulationRequest,
    current_user: User = Depends(simulate_cleanup),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    job = await AgentAdminService(db).start_cleanup_simulation(
        str(current_user.tenant_id),
        agent_id,
        server_id=body.server_id,
        container_folder=body.container_folder,
        max_properties=body.max_properties,
    )
    await db.commit()
    return {"jobId": str(job.id)}


@router.post("/{agent_id}/cleanup/quarantine", status_code=status.HTTP_202_ACCEPTED)
async def execute_agent_cleanup(
    agent_id: str,
    body: CleanupExecutionRequest,
    current_user: User = Depends(execute_cleanup),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    job = await AgentAdminService(db).start_cleanup_quarantine(
        str(current_user.tenant_id),
        agent_id,
        simulation_id=body.simulation_id,
        manifest_hash=body.manifest_hash,
    )
    await db.commit()
    return {"jobId": str(job.id)}


@router.post("/{agent_id}/cleanup/restore", status_code=status.HTTP_202_ACCEPTED)
async def restore_agent_quarantine(
    agent_id: str,
    body: QuarantineActionRequest,
    current_user: User = Depends(execute_cleanup),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    job = await AgentAdminService(db).start_quarantine_action(
        str(current_user.tenant_id),
        agent_id,
        command_type="restore_quarantine_item",
        server_id=body.server_id,
        execution_id=body.execution_id,
        relative_path=body.relative_path,
    )
    await db.commit()
    return {"jobId": str(job.id)}


@router.post("/{agent_id}/cleanup/purge", status_code=status.HTTP_202_ACCEPTED)
async def purge_agent_quarantine(
    agent_id: str,
    body: QuarantineActionRequest,
    current_user: User = Depends(purge_cleanup),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    job = await AgentAdminService(db).start_quarantine_action(
        str(current_user.tenant_id),
        agent_id,
        command_type="purge_quarantine_items",
        server_id=body.server_id,
        execution_id=body.execution_id,
    )
    await db.commit()
    return {"jobId": str(job.id)}


@router.put("/{agent_id}/configuration")
async def save_agent_configuration(
    agent_id: str,
    body: ConfigurationRequest,
    current_user: User = Depends(manage_config),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    server = await AgentAdminService(db).save_configuration(
        str(current_user.tenant_id),
        agent_id,
        name=body.name,
        root=body.root,
        target_folders=body.target_folders,
        target_files=body.target_files,
        validation_job_id=body.validation_job_id,
        server_id=body.server_id,
    )
    await db.commit()
    return server_payload(server)


@router.get("/jobs/{job_id}")
async def get_agent_job(
    job_id: str,
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    return await AgentAdminService(db).get_job(str(current_user.tenant_id), job_id)


@router.post("/jobs/{job_id}/cancel")
async def cancel_agent_job(
    job_id: str,
    current_user: User = Depends(execute_cleanup),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    result = await AgentAdminService(db).cancel_job(
        str(current_user.tenant_id), job_id
    )
    await db.commit()
    return result
