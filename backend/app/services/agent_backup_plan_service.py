from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.errors import DomainError, NotFoundError
from app.core.scheduler import scheduler
from app.models.agent_backup_plan import AgentBackupPlan
from app.models.backup import Backup, BackupStatus, BackupType
from app.repositories.cleanup_repository import tenant_uuid
from app.services.agent_operation_service import AgentOperationService


DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def serialize_agent_plan(item: AgentBackupPlan) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "agentId": str(item.agent_id),
        "sqlProfileId": item.sql_profile_id,
        "destinationProfileId": item.destination_profile_id,
        "databaseNames": item.database_names,
        "fullDays": item.full_days,
        "differentialDays": item.differential_days,
        "hourUtc": item.hour_utc,
        "enabled": item.enabled,
        "lastRunAt": item.last_run_at.isoformat() if item.last_run_at else None,
        "createdAt": item.created_at.isoformat(),
    }


def _validate_days(full_days: list[int], differential_days: list[int]) -> tuple[list[int], list[int]]:
    full = sorted(set(full_days))
    differential = sorted(set(differential_days))
    if not full:
        raise DomainError("BACKUP_PLAN_FULL_REQUIRED", "Seleccione al menos un día Full", 422)
    if any(day < 0 or day > 6 for day in full + differential):
        raise DomainError("BACKUP_PLAN_DAY_INVALID", "Los días del plan no son válidos", 422)
    if set(full) & set(differential):
        raise DomainError("BACKUP_PLAN_DAY_CONFLICT", "Un día no puede ser Full y Diferencial", 422)
    return full, differential


class AgentBackupPlanService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, tenant_id: str) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(AgentBackupPlan)
            .where(AgentBackupPlan.tenant_id == tenant_uuid(tenant_id))
            .order_by(AgentBackupPlan.created_at.desc())
        )
        return [serialize_agent_plan(item) for item in result.scalars().all()]

    async def create(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        full, differential = _validate_days(data["fullDays"], data["differentialDays"])
        names = list(dict.fromkeys(name.strip() for name in data["databaseNames"] if name.strip()))
        if not names or len(names) > 100:
            raise DomainError("BACKUP_DATABASE_SELECTION_INVALID", "Seleccione entre 1 y 100 bases de datos", 422)
        hour = int(data.get("hourUtc", 8))
        if hour < 0 or hour > 23:
            raise DomainError("BACKUP_PLAN_HOUR_INVALID", "La hora UTC no es válida", 422)
        # Verifica ahora que el agente y los perfiles declarados existen.
        operations = AgentOperationService(self.db)
        agent = await operations._agent(tenant_id, data["agentId"], require_online=False)
        operations._require_profile(agent, "sqlInstances", data["sqlProfileId"])
        if data.get("destinationProfileId"):
            operations._require_profile(agent, "backupDestinations", data["destinationProfileId"])
        item = AgentBackupPlan(
            tenant_id=tenant_uuid(tenant_id),
            agent_id=agent.id,
            sql_profile_id=data["sqlProfileId"],
            destination_profile_id=data.get("destinationProfileId"),
            database_names=names,
            full_days=full,
            differential_days=differential,
            hour_utc=hour,
            enabled=bool(data.get("enabled", True)),
        )
        self.db.add(item)
        await self.db.flush()
        if item.enabled:
            register_agent_plan(item)
        return serialize_agent_plan(item)

    async def delete(self, tenant_id: str, plan_id: str) -> None:
        item = await self._get(tenant_id, plan_id)
        remove_agent_plan(str(item.id))
        await self.db.delete(item)

    async def _get(self, tenant_id: str, plan_id: str) -> AgentBackupPlan:
        try:
            parsed = uuid.UUID(plan_id)
        except ValueError:
            raise NotFoundError("Plan de backup") from None
        item = (
            await self.db.execute(
                select(AgentBackupPlan).where(
                    AgentBackupPlan.id == parsed,
                    AgentBackupPlan.tenant_id == tenant_uuid(tenant_id),
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise NotFoundError("Plan de backup")
        return item


async def _run_agent_plan(plan_id: str, requested_type: str) -> None:
    async with AsyncSessionLocal() as db:
        item = (
            await db.execute(select(AgentBackupPlan).where(AgentBackupPlan.id == uuid.UUID(plan_id)))
        ).scalar_one_or_none()
        if item is None or not item.enabled:
            return
        busy_rows = await db.execute(
            select(Backup.database_name).where(
                Backup.tenant_id == item.tenant_id,
                Backup.agent_id == item.agent_id,
                Backup.database_name.in_(item.database_names),
                Backup.status.in_([BackupStatus.pending, BackupStatus.running]),
            )
        )
        busy = set(busy_rows.scalars().all())
        available = [name for name in item.database_names if name not in busy]
        if not available:
            return
        operations = AgentOperationService(db)
        if requested_type == "full":
            await operations.start_backup_run(
                str(item.tenant_id), str(item.agent_id), sql_profile_id=item.sql_profile_id,
                database_names=available, backup_type="full", destination_profile_id=item.destination_profile_id,
            )
        else:
            prior_full_rows = await db.execute(
                select(Backup.database_name).where(
                    Backup.tenant_id == item.tenant_id,
                    Backup.agent_id == item.agent_id,
                    Backup.database_name.in_(available),
                    Backup.backup_type == BackupType.full,
                    Backup.status == BackupStatus.completed,
                ).distinct()
            )
            with_full = set(prior_full_rows.scalars().all())
            initial_full = [name for name in available if name not in with_full]
            differential = [name for name in available if name in with_full]
            if initial_full:
                await operations.start_backup_run(
                    str(item.tenant_id), str(item.agent_id), sql_profile_id=item.sql_profile_id,
                    database_names=initial_full, backup_type="full", destination_profile_id=item.destination_profile_id,
                    trigger_reason="full_initial_required",
                )
            if differential:
                await operations.start_backup_run(
                    str(item.tenant_id), str(item.agent_id), sql_profile_id=item.sql_profile_id,
                    database_names=differential, backup_type="differential", destination_profile_id=item.destination_profile_id,
                )
        item.last_run_at = datetime.now(timezone.utc)
        await db.commit()


def register_agent_plan(item: AgentBackupPlan) -> None:
    remove_agent_plan(str(item.id))
    for kind, days in (("full", item.full_days), ("differential", item.differential_days)):
        if not days:
            continue
        scheduler.add_job(
            _run_agent_plan,
            CronTrigger(day_of_week=",".join(DAY_NAMES[day] for day in days), hour=item.hour_utc, minute=0, timezone="UTC"),
            args=[str(item.id), kind],
            id=f"agent-backup-plan:{item.id}:{kind}",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )


def remove_agent_plan(plan_id: str) -> None:
    for kind in ("full", "differential"):
        job = scheduler.get_job(f"agent-backup-plan:{plan_id}:{kind}")
        if job:
            scheduler.remove_job(job.id)


async def load_agent_backup_plans() -> None:
    async with AsyncSessionLocal() as db:
        items = (
            await db.execute(select(AgentBackupPlan).where(AgentBackupPlan.enabled.is_(True)))
        ).scalars().all()
        for item in items:
            register_agent_plan(item)
