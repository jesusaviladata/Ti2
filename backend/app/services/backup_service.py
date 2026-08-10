import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.backup import Backup, BackupStatus, BackupType, BackupDestination
from app.services import sqlserver_service as ss


class BackupService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Queries ───────────────────────────────────────────────────────────────

    async def list_backups(self, tenant_id: str, skip: int = 0, limit: int = 50) -> tuple[list[Backup], int]:
        q = (
            select(Backup)
            .where(Backup.tenant_id == uuid.UUID(tenant_id))
            .order_by(Backup.created_at.desc())
            .offset(skip).limit(limit)
        )
        cq = select(func.count()).select_from(Backup).where(Backup.tenant_id == uuid.UUID(tenant_id))
        items = (await self.db.execute(q)).scalars().all()
        total = (await self.db.execute(cq)).scalar_one()
        return list(items), total

    async def get_backup(self, tenant_id: str, backup_id: str) -> Backup:
        result = await self.db.execute(
            select(Backup).where(and_(Backup.id == uuid.UUID(backup_id), Backup.tenant_id == uuid.UUID(tenant_id)))
        )
        b = result.scalar_one_or_none()
        if not b:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup no encontrado")
        return b

    async def list_databases(self) -> list[str]:
        return await ss.list_databases()

    # ── Commands ──────────────────────────────────────────────────────────────

    async def trigger_backup(
        self,
        tenant_id: str,
        database_name: str,
        backup_type: str,
        destination: str = "local",
    ) -> Backup:
        backup = Backup(
            tenant_id=uuid.UUID(tenant_id),
            database_name=database_name,
            backup_type=BackupType(backup_type),
            status=BackupStatus.pending,
            destination=BackupDestination(destination),
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(backup)
        await self.db.flush()
        backup_id = str(backup.id)
        await self.db.commit()

        # Run backup asynchronously — don't block the API response
        asyncio.ensure_future(
            self._run_backup(backup_id, tenant_id, database_name, backup_type)
        )
        return backup

    async def _run_backup(self, backup_id: str, tenant_id: str, db_name: str, backup_type: str):
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Backup).where(Backup.id == uuid.UUID(backup_id)))
            backup = result.scalar_one_or_none()
            if not backup:
                return

            backup.status = BackupStatus.running
            await db.commit()

            try:
                dest_path = ss.build_backup_path(db_name, backup_type)
                info = await ss.execute_backup(db_name, backup_type, dest_path)
                backup.file_path = info["file_path"]
                backup.file_size_bytes = info["file_size_bytes"]
                backup.sha256_hash = info["sha256_hash"]

                # Verificar que el backup sea restaurable antes de marcarlo completado.
                if settings.SQLSERVER_BACKUP_VERIFY:
                    await ss.verify_backup(info["file_path"])

                backup.status = BackupStatus.completed
                backup.finished_at = datetime.now(timezone.utc)
            except Exception as exc:
                backup.status = BackupStatus.failed
                backup.error_message = ss.safe_error(exc)
                backup.finished_at = datetime.now(timezone.utc)

            await db.commit()

    async def verify_integrity(self, tenant_id: str, backup_id: str) -> dict:
        backup = await self.get_backup(tenant_id, backup_id)
        if not backup.file_path:
            raise HTTPException(status_code=400, detail="Backup sin archivo registrado")
        result = await ss.verify_backup(backup.file_path)
        # Update hash if missing
        if not backup.sha256_hash and result.get("sha256_hash"):
            backup.sha256_hash = result["sha256_hash"]
            await self.db.commit()
        return result

    async def apply_retention(self, tenant_id: str, database_name: str, keep_count: int, keep_days: int) -> int:
        """Delete backups exceeding retention policy. Returns count deleted."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)

        q = (
            select(Backup)
            .where(
                and_(
                    Backup.tenant_id == uuid.UUID(tenant_id),
                    Backup.database_name == database_name,
                    Backup.status == BackupStatus.completed,
                    Backup.created_at < cutoff,
                )
            )
            .order_by(Backup.created_at.asc())
        )
        old_backups = (await self.db.execute(q)).scalars().all()
        deleted = 0
        for b in old_backups:
            await self.db.delete(b)
            deleted += 1
        await self.db.commit()
        return deleted
