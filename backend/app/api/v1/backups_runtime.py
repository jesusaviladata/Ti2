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
