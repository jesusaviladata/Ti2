from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.backup_serializers import serialize_backup as _serialize
from app.core.capabilities import Capability, require_capabilities
from app.core.database import get_db
from app.models.user import User
from app.services.backup_runtime_service import BackupRuntimeService
from app.services.backup_service import BackupService
from app.services.agent_operation_service import AgentOperationService
from app.services.agent_backup_plan_service import AgentBackupPlanService


router = APIRouter()
read_operation = require_capabilities(Capability.OPERATION_READ)
run_backup = require_capabilities(Capability.BACKUP_RUN)
manage_backup = require_capabilities(Capability.CONFIG_MANAGE)
purge_backup = require_capabilities(Capability.PURGE)


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


class AgentBackupRunBody(BaseModel):
    agent_id: str = Field(alias="agentId")
    sql_profile_id: str = Field(alias="sqlProfileId", min_length=1, max_length=128)
    database_names: list[str] = Field(alias="databaseNames", min_length=1, max_length=100)
    backup_type: Literal["full", "differential", "log"] = Field("full", alias="backupType")
    destination_profile_id: str | None = Field(None, alias="destinationProfileId", max_length=128)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class AgentBackupPlanBody(BaseModel):
    agent_id: str = Field(alias="agentId")
    sql_profile_id: str = Field(alias="sqlProfileId", min_length=1, max_length=128)
    destination_profile_id: str | None = Field(None, alias="destinationProfileId", max_length=128)
    database_names: list[str] = Field(alias="databaseNames", min_length=1, max_length=100)
    full_days: list[int] = Field(alias="fullDays", min_length=1, max_length=7)
    differential_days: list[int] = Field(default_factory=list, alias="differentialDays", max_length=7)
    hour_utc: int = Field(8, alias="hourUtc", ge=0, le=23)
    enabled: bool = True

    model_config = {"populate_by_name": True, "extra": "forbid"}


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


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def create_agent_backup_run(
    body: AgentBackupRunBody,
    current_user: User = Depends(run_backup),
    db: AsyncSession = Depends(get_db),
):
    job, records = await AgentOperationService(db).start_backup_run(
        str(current_user.tenant_id),
        body.agent_id,
        sql_profile_id=body.sql_profile_id,
        database_names=body.database_names,
        backup_type=body.backup_type,
        destination_profile_id=body.destination_profile_id,
    )
    await db.commit()
    return {"jobId": str(job.id), "backups": [_serialize(item) for item in records]}


@router.post("/{backup_id}/delivery/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_agent_backup_delivery(
    backup_id: str,
    current_user: User = Depends(run_backup),
    db: AsyncSession = Depends(get_db),
):
    job = await AgentOperationService(db).retry_backup_delivery(
        str(current_user.tenant_id), backup_id
    )
    await db.commit()
    return {"jobId": str(job.id)}


@router.get("/plans")
async def list_agent_backup_plans(
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    items = await AgentBackupPlanService(db).list(str(current_user.tenant_id))
    return {"items": items, "total": len(items)}


@router.post("/plans", status_code=status.HTTP_201_CREATED)
async def create_agent_backup_plan(
    body: AgentBackupPlanBody,
    current_user: User = Depends(manage_backup),
    db: AsyncSession = Depends(get_db),
):
    item = await AgentBackupPlanService(db).create(
        str(current_user.tenant_id), body.model_dump(by_alias=True)
    )
    await db.commit()
    return item


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_backup_plan(
    plan_id: str,
    current_user: User = Depends(manage_backup),
    db: AsyncSession = Depends(get_db),
):
    await AgentBackupPlanService(db).delete(str(current_user.tenant_id), plan_id)
    await db.commit()


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
