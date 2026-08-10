from __future__ import annotations

import asyncio
import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.errors import DomainError, NotFoundError
from app.core.scheduler import scheduler
from app.models.backup import (
    Backup,
    BackupDestination,
    BackupStatus,
    BackupType,
)
from app.models.backup_schedule import BackupSchedule
from app.repositories.cleanup_repository import tenant_uuid
from app.services.backup_service import BackupService
from app.services.connection_service import _connect
from app.services.sqlserver_service import safe_error


def serialize_schedule(item: BackupSchedule) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "databaseName": item.database_name,
        "backupType": item.backup_type,
        "destination": item.destination,
        "cronExpr": item.cron_expression,
        "retentionCount": item.retention_count,
        "retentionDays": item.retention_days,
        "enabled": item.is_active,
        "lastRunAt": item.last_run_at.isoformat() if item.last_run_at else None,
        "nextRunAt": item.next_run_at.isoformat() if item.next_run_at else None,
        "createdAt": item.created_at.isoformat(),
    }


def _validate_database(name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name):
        raise DomainError(
            "INVALID_DATABASE_NAME", "Nombre de base de datos inválido", 422
        )


def _hash_file(path: str) -> str:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _destination_path(
    database_name: str, backup_type: str, local_path: str | None
) -> str:
    root = Path(local_path or settings.SQLSERVER_BACKUP_PATH)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    extension = ".trn" if backup_type == "log" else ".bak"
    return str(root / f"{database_name}_{backup_type.upper()}_{timestamp}{extension}")


def _sync_backup(
    connection: dict[str, Any] | None,
    database_name: str,
    backup_type: str,
    path: str,
) -> dict[str, Any]:
    _validate_database(database_name)
    verb = "BACKUP LOG" if backup_type == "log" else "BACKUP DATABASE"
    differential = "DIFFERENTIAL, " if backup_type == "differential" else ""
    sql = (
        f"{verb} [{database_name}] TO DISK = ? WITH "
        f"{differential}FORMAT, INIT, CHECKSUM, STATS = 10"
    )
    if connection:
        with _connect(connection) as handle:
            handle.execute(sql, path)
            handle.commit()
            handle.execute("RESTORE VERIFYONLY FROM DISK = ? WITH CHECKSUM", path)
    else:
        from app.services.sqlserver_service import _conn

        with _conn() as handle:
            handle.execute(sql, path)
            handle.commit()
            handle.execute("RESTORE VERIFYONLY FROM DISK = ? WITH CHECKSUM", path)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    return {
        "file_path": path,
        "file_size_bytes": size,
        "sha256_hash": _hash_file(path),
    }


class BackupRuntimeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def trigger_many(
        self,
        tenant_id: str,
        database_names: list[str],
        backup_type: str,
        destination: str,
        local_path: str | None,
        connection: dict[str, Any] | None,
    ) -> list[Backup]:
        if not database_names:
            raise DomainError(
                "DATABASE_REQUIRED", "Seleccione al menos una base de datos", 422
            )
        records: list[Backup] = []
        for database_name in dict.fromkeys(database_names):
            _validate_database(database_name)
            record = Backup(
                tenant_id=tenant_uuid(tenant_id),
                database_name=database_name,
                backup_type=BackupType(backup_type),
                status=BackupStatus.pending,
                destination=BackupDestination(destination),
                started_at=datetime.now(timezone.utc),
            )
            self.db.add(record)
            records.append(record)
        await self.db.flush()
        await self.db.commit()
        for record in records:
            asyncio.create_task(
                self._run(
                    str(record.id),
                    record.database_name,
                    backup_type,
                    local_path,
                    connection,
                )
            )
        return records

    @staticmethod
    async def _run(
        backup_id: str,
        database_name: str,
        backup_type: str,
        local_path: str | None,
        connection: dict[str, Any] | None,
    ) -> None:
        async with AsyncSessionLocal() as db:
            record = (
                await db.execute(
                    select(Backup).where(Backup.id == uuid.UUID(backup_id))
                )
            ).scalar_one_or_none()
            if not record:
                return
            record.status = BackupStatus.running
            await db.commit()
            try:
                path = _destination_path(database_name, backup_type, local_path)
                info = await asyncio.to_thread(
                    _sync_backup,
                    connection,
                    database_name,
                    backup_type,
                    path,
                )
                record.file_path = info["file_path"]
                record.file_size_bytes = info["file_size_bytes"]
                record.sha256_hash = info["sha256_hash"]
                record.status = BackupStatus.completed
            except Exception as exc:
                record.status = BackupStatus.failed
                record.error_message = safe_error(exc)
            record.finished_at = datetime.now(timezone.utc)
            await db.commit()

    async def list_schedules(self, tenant_id: str) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(BackupSchedule)
            .where(BackupSchedule.tenant_id == tenant_uuid(tenant_id))
            .order_by(BackupSchedule.created_at.desc())
        )
        return [serialize_schedule(item) for item in result.scalars().all()]

    async def create_schedule(
        self, tenant_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            trigger = CronTrigger.from_crontab(data["cronExpr"], timezone="UTC")
        except ValueError as exc:
            raise DomainError("INVALID_CRON", str(exc), 422) from exc
        item = BackupSchedule(
            tenant_id=tenant_uuid(tenant_id),
            database_name=data["databaseName"],
            backup_type=data["backupType"],
            destination=data["destination"],
            cron_expression=data["cronExpr"],
            retention_count=data["retentionCount"],
            retention_days=data["retentionDays"],
            is_active=data["enabled"],
            next_run_at=trigger.get_next_fire_time(
                None, datetime.now(timezone.utc)
            ),
        )
        self.db.add(item)
        await self.db.flush()
        if item.is_active:
            register_backup_schedule(item)
        return serialize_schedule(item)

    async def update_schedule(
        self, tenant_id: str, schedule_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        item = await self._get_schedule(tenant_id, schedule_id)
        mapping = {
            "databaseName": "database_name",
            "backupType": "backup_type",
            "destination": "destination",
            "cronExpr": "cron_expression",
            "retentionCount": "retention_count",
            "retentionDays": "retention_days",
            "enabled": "is_active",
        }
        for source, target in mapping.items():
            if source in data:
                setattr(item, target, data[source])
        try:
            trigger = CronTrigger.from_crontab(
                item.cron_expression, timezone="UTC"
            )
        except ValueError as exc:
            raise DomainError("INVALID_CRON", str(exc), 422) from exc
        item.next_run_at = (
            trigger.get_next_fire_time(None, datetime.now(timezone.utc))
            if item.is_active
            else None
        )
        remove_backup_schedule(str(item.id))
        if item.is_active:
            register_backup_schedule(item)
        return serialize_schedule(item)

    async def delete_schedule(self, tenant_id: str, schedule_id: str) -> None:
        item = await self._get_schedule(tenant_id, schedule_id)
        remove_backup_schedule(str(item.id))
        await self.db.delete(item)

    async def _get_schedule(
        self, tenant_id: str, schedule_id: str
    ) -> BackupSchedule:
        result = await self.db.execute(
            select(BackupSchedule).where(
                BackupSchedule.id == uuid.UUID(schedule_id),
                BackupSchedule.tenant_id == tenant_uuid(tenant_id),
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise NotFoundError("Programación de respaldo")
        return item


async def _run_scheduled_backup(schedule_id: str) -> None:
    async with AsyncSessionLocal() as db:
        item = (
            await db.execute(
                select(BackupSchedule).where(
                    BackupSchedule.id == uuid.UUID(schedule_id)
                )
            )
        ).scalar_one_or_none()
        if not item or not item.is_active:
            return
        item.last_run_at = datetime.now(timezone.utc)
        job = scheduler.get_job(f"backup:{item.id}")
        item.next_run_at = job.next_run_time if job else None
        await db.commit()
        await BackupService(db).trigger_backup(
            str(item.tenant_id),
            item.database_name,
            item.backup_type,
            item.destination,
        )


def register_backup_schedule(item: BackupSchedule) -> None:
    scheduler.add_job(
        _run_scheduled_backup,
        CronTrigger.from_crontab(item.cron_expression, timezone="UTC"),
        args=[str(item.id)],
        id=f"backup:{item.id}",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )


def remove_backup_schedule(schedule_id: str) -> None:
    job = scheduler.get_job(f"backup:{schedule_id}")
    if job:
        scheduler.remove_job(job.id)


async def load_backup_schedules() -> None:
    async with AsyncSessionLocal() as db:
        items = (
            await db.execute(
                select(BackupSchedule).where(
                    BackupSchedule.is_active.is_(True)
                )
            )
        ).scalars()
        for item in items:
            register_backup_schedule(item)
