from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.operations import (
    CleanupExecution,
    CleanupFolder,
    CleanupRule,
    CleanupSchedule,
    CleanupSimulation,
    CleanupTrashItem,
)


def tenant_uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class CleanupRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_folders(self, tenant_id: str) -> list[CleanupFolder]:
        result = await self.db.execute(
            select(CleanupFolder)
            .where(CleanupFolder.tenant_id == tenant_uuid(tenant_id))
            .order_by(CleanupFolder.label, CleanupFolder.path)
        )
        return list(result.scalars().all())

    async def get_folder(self, tenant_id: str, folder_id: str) -> CleanupFolder:
        result = await self.db.execute(
            select(CleanupFolder).where(
                CleanupFolder.id == uuid.UUID(folder_id),
                CleanupFolder.tenant_id == tenant_uuid(tenant_id),
            )
        )
        folder = result.scalar_one_or_none()
        if not folder:
            raise NotFoundError("Carpeta")
        return folder

    async def list_rules(self, tenant_id: str) -> list[CleanupRule]:
        result = await self.db.execute(
            select(CleanupRule)
            .where(CleanupRule.tenant_id == tenant_uuid(tenant_id))
            .order_by(CleanupRule.name)
        )
        return list(result.scalars().all())

    async def get_rule(self, tenant_id: str, rule_id: str) -> CleanupRule:
        result = await self.db.execute(
            select(CleanupRule).where(
                CleanupRule.id == uuid.UUID(rule_id),
                CleanupRule.tenant_id == tenant_uuid(tenant_id),
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise NotFoundError("Regla")
        return rule

    async def get_rules_for_folder(
        self, tenant_id: str, folder_id: str
    ) -> list[CleanupRule]:
        result = await self.db.execute(
            select(CleanupRule).where(
                CleanupRule.tenant_id == tenant_uuid(tenant_id),
                CleanupRule.enabled.is_(True),
                (CleanupRule.folder_id == uuid.UUID(folder_id))
                | (CleanupRule.folder_id.is_(None)),
            )
        )
        return list(result.scalars().all())

    async def latest_simulation(
        self,
        tenant_id: str,
        user_id: str,
        simulation_id: str | None = None,
    ) -> CleanupSimulation:
        query = select(CleanupSimulation).where(
            CleanupSimulation.tenant_id == tenant_uuid(tenant_id),
            CleanupSimulation.user_id == uuid.UUID(user_id),
            CleanupSimulation.consumed_at.is_(None),
            CleanupSimulation.expires_at > datetime.now(timezone.utc),
        )
        if simulation_id:
            query = query.where(CleanupSimulation.id == uuid.UUID(simulation_id))
        query = query.order_by(CleanupSimulation.created_at.desc()).limit(1)
        simulation = (await self.db.execute(query)).scalar_one_or_none()
        if not simulation:
            raise NotFoundError("Simulación vigente")
        return simulation

    async def list_trash(self, tenant_id: str) -> list[CleanupTrashItem]:
        result = await self.db.execute(
            select(CleanupTrashItem)
            .where(
                CleanupTrashItem.tenant_id == tenant_uuid(tenant_id),
                CleanupTrashItem.restored_at.is_(None),
                CleanupTrashItem.purged_at.is_(None),
            )
            .order_by(CleanupTrashItem.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_trash(self, tenant_id: str, item_id: str) -> CleanupTrashItem:
        result = await self.db.execute(
            select(CleanupTrashItem).where(
                CleanupTrashItem.id == uuid.UUID(item_id),
                CleanupTrashItem.tenant_id == tenant_uuid(tenant_id),
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise NotFoundError("Elemento de cuarentena")
        return item

    async def list_history(
        self, tenant_id: str, skip: int, limit: int
    ) -> tuple[list[CleanupExecution], int]:
        condition = CleanupExecution.tenant_id == tenant_uuid(tenant_id)
        items = (
            await self.db.execute(
                select(CleanupExecution)
                .where(condition)
                .order_by(CleanupExecution.started_at.desc())
                .offset(skip)
                .limit(limit)
            )
        ).scalars().all()
        total = (
            await self.db.execute(
                select(func.count()).select_from(CleanupExecution).where(condition)
            )
        ).scalar_one()
        return list(items), total

    async def list_schedules(self, tenant_id: str) -> list[CleanupSchedule]:
        result = await self.db.execute(
            select(CleanupSchedule)
            .where(CleanupSchedule.tenant_id == tenant_uuid(tenant_id))
            .order_by(CleanupSchedule.name)
        )
        return list(result.scalars().all())

    async def get_schedule(self, tenant_id: str, schedule_id: str) -> CleanupSchedule:
        result = await self.db.execute(
            select(CleanupSchedule).where(
                CleanupSchedule.id == uuid.UUID(schedule_id),
                CleanupSchedule.tenant_id == tenant_uuid(tenant_id),
            )
        )
        schedule = result.scalar_one_or_none()
        if not schedule:
            raise NotFoundError("Programación")
        return schedule
