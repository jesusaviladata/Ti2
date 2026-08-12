from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.backup_serializers import serialize_backup as _serialize
from app.core.capabilities import Capability, require_capabilities
from app.core.database import get_db
from app.models.user import User
from app.services.backup_runtime_service import BackupRuntimeService
from app.services.backup_service import BackupService
from app.services.agent_admin_service import AgentAdminService
from app.services.agent_backup_service import AgentBackupService
from app.core.config import settings
from app.core.errors import DomainError


router = APIRouter()
read_operation = require_capabilities(Capability.OPERATION_READ)
run_backup = require_capabilities(Capability.BACKUP_RUN)
manage_backup = require_capabilities(Capability.CONFIG_MANAGE)
purge_backup = require_capabilities(Capability.PURGE)
DatabaseName = Annotated[
    str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
]


class ConnectionBody(BaseModel):
    server: str
    port: int = Field(1433, ge=1, le=65535)
    authentication: Literal["sql", "windows"] = "sql"
    username: str = ""
    password: str = ""
    driver: str = "ODBC Driver 17 for SQL Server"


class ManualBackupBody(BaseModel):
    database_names: list[str]
    backup_type: Literal["full", "differential", "log"] = "full"
    destination: Literal["local", "nas", "secondary_server"] = "local"
    local_path: str | None = None
    connection: ConnectionBody | None = None


class AgentDatabaseBody(BaseModel):
    agent_id: str
    sql_profile_id: str = Field(min_length=1, max_length=64)


class AgentManualBackupBody(BaseModel):
    agent_id: str
    sql_profile_id: str = Field(min_length=1, max_length=64)
    database_names: list[DatabaseName] = Field(min_length=1, max_length=100)
    backup_type: Literal["full", "differential", "log"] = "full"
    destination_profile_id: str | None = Field(None, max_length=64)


def _require_agent_module() -> None:
    if not settings.AGENT_MODULE_ENABLED:
        raise DomainError(
            "AGENT_MODULE_DISABLED", "El modulo de agentes no esta habilitado", 503
        )


class RetentionBody(BaseModel):
    database_name: str
    keep_count: int = Field(10, ge=0)
    keep_days: int = Field(30, ge=0)


class ScheduleBody(BaseModel):
    databaseName: str
    backupType: Literal["full", "differential", "log"] = "full"
    destination: Literal["local", "nas", "secondary_server"] = "local"
    cronExpr: str
    retentionCount: int = Field(10, ge=0)
    retentionDays: int = Field(30, ge=0)
    enabled: bool = True


class ScheduleUpdateBody(BaseModel):
    databaseName: str | None = None
    backupType: Literal["full", "differential", "log"] | None = None
    destination: Literal["local", "nas", "secondary_server"] | None = None
    cronExpr: str | None = None
    retentionCount: int | None = Field(None, ge=0)
    retentionDays: int | None = Field(None, ge=0)
    enabled: bool | None = None


@router.get("")
async def list_backups(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    items, total = await BackupService(db).list_backups(
        str(current_user.tenant_id), skip, limit
    )
    return {
        "items": [_serialize(item) for item in items],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/databases")
async def list_databases(
    _: User = Depends(read_operation), db: AsyncSession = Depends(get_db)
):
    return {
        "databases": await BackupService(db).list_databases(),
        "connected": True,
    }


@router.get("/agents")
async def list_backup_agents(
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    _require_agent_module()
    items = await AgentBackupService(db).list_agents(str(current_user.tenant_id))
    return {"items": items, "total": len(items)}


@router.post("/agent-databases", status_code=status.HTTP_202_ACCEPTED)
async def list_agent_databases(
    body: AgentDatabaseBody,
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    _require_agent_module()
    job = await AgentBackupService(db).start_database_list(
        str(current_user.tenant_id), body.agent_id, body.sql_profile_id
    )
    await db.commit()
    return {"jobId": str(job.id)}


@router.post("/manual", status_code=status.HTTP_202_ACCEPTED)
async def trigger_manual_backup(
    body: ManualBackupBody,
    current_user: User = Depends(run_backup),
    db: AsyncSession = Depends(get_db),
):
    records = await BackupRuntimeService(db).trigger_many(
        str(current_user.tenant_id),
        body.database_names,
        body.backup_type,
        body.destination,
        body.local_path,
        body.connection.model_dump() if body.connection else None,
    )
    return {"backups": [_serialize(item) for item in records]}


@router.post("/manual-agent", status_code=status.HTTP_202_ACCEPTED)
async def trigger_agent_backup(
    body: AgentManualBackupBody,
    current_user: User = Depends(run_backup),
    db: AsyncSession = Depends(get_db),
):
    _require_agent_module()
    job, records = await AgentBackupService(db).start_backup(
        str(current_user.tenant_id),
        body.agent_id,
        sql_profile_id=body.sql_profile_id,
        database_names=body.database_names,
        backup_type=body.backup_type,
        destination_profile_id=body.destination_profile_id,
    )
    await db.commit()
    return {
        "jobId": str(job.id),
        "backups": [_serialize(item) for item in records],
    }


@router.get("/agent-jobs/{job_id}")
async def get_backup_agent_job(
    job_id: str,
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    _require_agent_module()
    return await AgentAdminService(db).get_job(str(current_user.tenant_id), job_id)


@router.get("/{backup_id}/status")
async def backup_status(
    backup_id: str,
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    return _serialize(
        await BackupService(db).get_backup(
            str(current_user.tenant_id), backup_id
        )
    )


@router.get("/integrity/{backup_id}")
async def check_integrity(
    backup_id: str,
    current_user: User = Depends(run_backup),
    db: AsyncSession = Depends(get_db),
):
    return await BackupService(db).verify_integrity(
        str(current_user.tenant_id), backup_id
    )


@router.delete("/purge")
async def purge_backups(
    body: RetentionBody,
    current_user: User = Depends(purge_backup),
    db: AsyncSession = Depends(get_db),
):
    deleted = await BackupService(db).apply_retention(
        str(current_user.tenant_id),
        body.database_name,
        body.keep_count,
        body.keep_days,
    )
    return {"deleted": deleted}


@router.get("/logs")
async def backup_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    items, total = await BackupService(db).list_backups(
        str(current_user.tenant_id), skip, limit
    )
    return {"items": [_serialize(item) for item in items], "total": total}


@router.get("/schedules")
async def list_schedules(
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    items = await BackupRuntimeService(db).list_schedules(
        str(current_user.tenant_id)
    )
    return {"items": items, "total": len(items)}


@router.post("/schedules", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleBody,
    current_user: User = Depends(manage_backup),
    db: AsyncSession = Depends(get_db),
):
    return await BackupRuntimeService(db).create_schedule(
        str(current_user.tenant_id), body.model_dump()
    )


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdateBody,
    current_user: User = Depends(manage_backup),
    db: AsyncSession = Depends(get_db),
):
    return await BackupRuntimeService(db).update_schedule(
        str(current_user.tenant_id),
        schedule_id,
        body.model_dump(exclude_unset=True),
    )


@router.delete(
    "/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_schedule(
    schedule_id: str,
    current_user: User = Depends(manage_backup),
    db: AsyncSession = Depends(get_db),
):
    await BackupRuntimeService(db).delete_schedule(
        str(current_user.tenant_id), schedule_id
    )
