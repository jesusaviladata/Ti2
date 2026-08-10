from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_log import AccessLog
from app.models.backup import Backup, BackupStatus
from app.models.operations import CleanupExecution, Notification
from app.models.user import User
from app.repositories.cleanup_repository import tenant_uuid


def _start_of_day(days_ago: int = 0) -> datetime:
    target = date.today() - timedelta(days=days_ago)
    return datetime.combine(target, datetime.min.time(), timezone.utc)


class InsightsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def summary(self, tenant_id: str) -> dict[str, int]:
        tenant = tenant_uuid(tenant_id)
        today = _start_of_day()
        backups_today = (
            await self.db.execute(
                select(func.count())
                .select_from(Backup)
                .where(
                    Backup.tenant_id == tenant,
                    Backup.status == BackupStatus.completed,
                    Backup.created_at >= today,
                )
            )
        ).scalar_one()
        failed = (
            await self.db.execute(
                select(func.count())
                .select_from(Backup)
                .where(
                    Backup.tenant_id == tenant,
                    Backup.status == BackupStatus.failed,
                )
            )
        ).scalar_one()
        active = (
            await self.db.execute(
                select(func.count())
                .select_from(AccessLog)
                .where(
                    AccessLog.tenant_id == tenant,
                    AccessLog.status == "active",
                )
            )
        ).scalar_one()
        suspicious = (
            await self.db.execute(
                select(func.count())
                .select_from(AccessLog)
                .where(
                    AccessLog.tenant_id == tenant,
                    AccessLog.is_suspicious.is_(True),
                    AccessLog.status == "active",
                )
            )
        ).scalar_one()
        return {
            "backups_today": backups_today,
            "failed_backups": failed,
            "active_sessions": active,
            "critical_alerts": failed + suspicious,
        }

    async def backup_chart(
        self, tenant_id: str, days: int = 14
    ) -> list[dict[str, Any]]:
        tenant = tenant_uuid(tenant_id)
        start = _start_of_day(days - 1)
        rows = (
            await self.db.execute(
                select(Backup.created_at, Backup.status).where(
                    Backup.tenant_id == tenant, Backup.created_at >= start
                )
            )
        ).all()
        by_day: dict[str, dict[str, Any]] = {}
        for offset in range(days - 1, -1, -1):
            day = (date.today() - timedelta(days=offset)).isoformat()
            by_day[day] = {
                "date": day,
                "completed": 0,
                "failed": 0,
                "running": 0,
            }
        for created_at, status in rows:
            day = created_at.date().isoformat()
            if day in by_day and status.value in by_day[day]:
                by_day[day][status.value] += 1
        return list(by_day.values())

    async def activity(
        self, tenant_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        tenant = tenant_uuid(tenant_id)
        backups = (
            await self.db.execute(
                select(Backup)
                .where(Backup.tenant_id == tenant)
                .order_by(Backup.created_at.desc())
                .limit(limit)
            )
        ).scalars()
        accesses = (
            await self.db.execute(
                select(AccessLog)
                .where(AccessLog.tenant_id == tenant)
                .order_by(AccessLog.started_at.desc())
                .limit(limit)
            )
        ).scalars()
        events = [
            {
                "id": str(item.id),
                "kind": "backup",
                "label": f"{item.database_name} · {item.backup_type.value}",
                "status": item.status.value,
                "ts": item.created_at.isoformat(),
            }
            for item in backups
        ]
        events.extend(
            {
                "id": str(item.id),
                "kind": "access",
                "label": f"{item.tool} · {item.server_name}",
                "status": "alert" if item.is_suspicious else item.status,
                "ts": item.started_at.isoformat(),
            }
            for item in accesses
        )
        events.sort(key=lambda item: item["ts"], reverse=True)
        return events[:limit]

    async def notifications(self, tenant_id: str) -> list[dict[str, Any]]:
        tenant = tenant_uuid(tenant_id)
        persisted = (
            await self.db.execute(
                select(Notification)
                .where(Notification.tenant_id == tenant)
                .order_by(Notification.created_at.desc())
                .limit(100)
            )
        ).scalars()
        result = [
            {
                "id": str(item.id),
                "kind": item.kind,
                "title": item.title,
                "body": item.message,
                "ts": item.created_at.isoformat(),
                "severity": item.severity,
                "read": item.is_read,
            }
            for item in persisted
        ]
        failed_backups = (
            await self.db.execute(
                select(Backup)
                .where(
                    Backup.tenant_id == tenant,
                    Backup.status == BackupStatus.failed,
                )
                .order_by(Backup.created_at.desc())
                .limit(50)
            )
        ).scalars()
        result.extend(
            {
                "id": f"backup:{item.id}",
                "kind": "backup_fail",
                "title": f"Respaldo fallido: {item.database_name}",
                "body": item.error_message or "La ejecución no se completó",
                "ts": item.created_at.isoformat(),
            }
            for item in failed_backups
        )
        suspicious = (
            await self.db.execute(
                select(AccessLog)
                .where(
                    AccessLog.tenant_id == tenant,
                    AccessLog.is_suspicious.is_(True),
                )
                .order_by(AccessLog.started_at.desc())
                .limit(50)
            )
        ).scalars()
        result.extend(
            {
                "id": f"access:{item.id}",
                "kind": "suspicious",
                "title": f"Acceso sospechoso: {item.server_name}",
                "body": f"{item.tool} desde {item.ip_address}",
                "ts": item.started_at.isoformat(),
            }
            for item in suspicious
        )
        result.sort(key=lambda item: item["ts"], reverse=True)
        return result[:100]

    async def create_test_notification(
        self, tenant_id: str, user_id: str
    ) -> dict[str, Any]:
        item = Notification(
            tenant_id=tenant_uuid(tenant_id),
            user_id=uuid.UUID(user_id),
            kind="test",
            title="Notificación de prueba",
            message="El centro de notificaciones funciona correctamente.",
            severity="info",
            metadata_json={},
        )
        self.db.add(item)
        await self.db.flush()
        return {
            "id": str(item.id),
            "kind": item.kind,
            "title": item.title,
            "body": item.message,
            "ts": item.created_at.isoformat(),
        }

    async def backup_report(self, tenant_id: str) -> dict[str, Any]:
        items = (
            await self.db.execute(
                select(Backup)
                .where(Backup.tenant_id == tenant_uuid(tenant_id))
                .order_by(Backup.created_at.desc())
                .limit(1000)
            )
        ).scalars()
        rows = [
            {
                "id": str(item.id),
                "database": item.database_name,
                "type": item.backup_type.value,
                "status": item.status.value,
                "bytes": item.file_size_bytes or 0,
                "createdAt": item.created_at.isoformat(),
            }
            for item in items
        ]
        return {
            "items": rows,
            "total": len(rows),
            "bytes": sum(item["bytes"] for item in rows),
        }

    async def access_report(self, tenant_id: str) -> dict[str, Any]:
        from app.services.access_service import AccessService

        items = await AccessService(self.db).list(tenant_id)
        return {"items": items, "total": len(items)}

    async def cleanup_report(self, tenant_id: str) -> dict[str, Any]:
        items = (
            await self.db.execute(
                select(CleanupExecution)
                .where(CleanupExecution.tenant_id == tenant_uuid(tenant_id))
                .order_by(CleanupExecution.started_at.desc())
                .limit(1000)
            )
        ).scalars()
        rows = [
            {
                "id": str(item.id),
                "kind": item.kind,
                "status": item.status,
                "files": item.files_deleted,
                "bytes": item.bytes_freed,
                "errors": item.errors_count,
                "startedAt": item.started_at.isoformat(),
            }
            for item in items
        ]
        return {"items": rows, "total": len(rows)}

    async def search(
        self, tenant_id: str, query: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        tenant = tenant_uuid(tenant_id)
        pattern = f"%{query.strip()}%"
        backups = (
            await self.db.execute(
                select(Backup)
                .where(
                    Backup.tenant_id == tenant,
                    Backup.database_name.ilike(pattern),
                )
                .limit(limit)
            )
        ).scalars()
        accesses = (
            await self.db.execute(
                select(AccessLog)
                .where(
                    AccessLog.tenant_id == tenant,
                    or_(
                        AccessLog.server_name.ilike(pattern),
                        AccessLog.client_name.ilike(pattern),
                        AccessLog.ip_address.ilike(pattern),
                    ),
                )
                .limit(limit)
            )
        ).scalars()
        results = [
            {
                "id": str(item.id),
                "type": "backup",
                "title": item.database_name,
                "subtitle": item.status.value,
                "href": "/dashboard/backups",
            }
            for item in backups
        ]
        results.extend(
            {
                "id": str(item.id),
                "type": "access",
                "title": item.server_name,
                "subtitle": f"{item.tool} · {item.ip_address}",
                "href": "/dashboard/access",
            }
            for item in accesses
        )
        return results[:limit]
