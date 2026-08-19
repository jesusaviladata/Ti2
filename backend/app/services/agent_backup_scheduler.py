from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.core.scheduler import scheduler
from app.models.operations import AgentBackupPlan, RemoteAgent
from app.repositories.cleanup_repository import tenant_uuid
from app.services.agent_backup_service import AgentBackupService


FULL_WEEKDAYS = frozenset({0, 2, 4})  # Monday, Wednesday, Friday
DIFFERENTIAL_WEEKDAYS = frozenset({1, 3})  # Tuesday, Thursday
DATABASE_BATCH_SIZE = 100
_DATABASE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_LOCAL_TIME = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def backup_type_for_weekday(weekday: int) -> str | None:
    if weekday in FULL_WEEKDAYS:
        return "full"
    if weekday in DIFFERENTIAL_WEEKDAYS:
        return "differential"
    return None


def _time_parts(value: str) -> tuple[int, int]:
    if not _LOCAL_TIME.fullmatch(value):
        raise DomainError("INVALID_BACKUP_TIME", "La hora debe usar el formato HH:MM", 422)
    hour, minute = value.split(":", 1)
    return int(hour), int(minute)


def _timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise DomainError("INVALID_TIMEZONE", "La zona horaria no es valida", 422) from exc


def trigger_for_plan(local_time: str, timezone_name: str) -> CronTrigger:
    hour, minute = _time_parts(local_time)
    return CronTrigger(
        day_of_week="mon-fri",
        hour=hour,
        minute=minute,
        timezone=_timezone(timezone_name),
    )


def next_run_for_plan(
    local_time: str,
    timezone_name: str,
    now: datetime | None = None,
) -> datetime | None:
    current = now or datetime.now(timezone.utc)
    return trigger_for_plan(local_time, timezone_name).get_next_fire_time(None, current)


def serialize_agent_backup_plan(item: AgentBackupPlan) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "name": item.name,
        "agentId": str(item.agent_id),
        "sqlProfileId": item.sql_profile_id,
        "destinationProfileId": item.destination_profile_id,
        "databaseNames": list(item.database_names or []),
        "localTime": item.local_time,
        "timezone": item.timezone_name,
        "enabled": item.is_active,
        "fullDays": ["lunes", "miercoles", "viernes"],
        "differentialDays": ["martes", "jueves"],
        "lastRunAt": item.last_run_at.isoformat() if item.last_run_at else None,
        "nextRunAt": item.next_run_at.isoformat() if item.next_run_at else None,
        "createdAt": item.created_at.isoformat(),
    }


class AgentBackupPlanService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, tenant_id: str) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(AgentBackupPlan)
            .where(AgentBackupPlan.tenant_id == tenant_uuid(tenant_id))
            .order_by(AgentBackupPlan.created_at.desc())
        )
        return [serialize_agent_backup_plan(item) for item in result.scalars().all()]

    async def create(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        tenant_id_value = tenant_uuid(tenant_id)
        agent = await self._agent(tenant_id_value, data["agentId"])
        names = self._database_names(data["databaseNames"])
        self._validate_profiles(
            agent,
            data["sqlProfileId"],
            data.get("destinationProfileId"),
        )
        timezone_name = str(data.get("timezone") or "America/Mexico_City")
        local_time = str(data.get("localTime") or "02:00")
        next_run = next_run_for_plan(local_time, timezone_name)
        duplicate = await self.db.scalar(
            select(AgentBackupPlan.id).where(
                AgentBackupPlan.tenant_id == tenant_id_value,
                AgentBackupPlan.name == str(data["name"]).strip(),
            )
        )
        if duplicate:
            raise ConflictError(
                "Ya existe un plan de backup con ese nombre",
                code="BACKUP_PLAN_EXISTS",
            )
        item = AgentBackupPlan(
            tenant_id=tenant_id_value,
            name=str(data["name"]).strip(),
            agent_id=agent.id,
            sql_profile_id=str(data["sqlProfileId"]),
            destination_profile_id=data.get("destinationProfileId") or None,
            database_names=names,
            local_time=local_time,
            timezone_name=timezone_name,
            is_active=bool(data.get("enabled", True)),
            next_run_at=next_run if data.get("enabled", True) else None,
        )
        self.db.add(item)
        await self.db.flush()
        if item.is_active:
            register_agent_backup_plan(item)
        return serialize_agent_backup_plan(item)

    async def update(
        self, tenant_id: str, plan_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        item = await self._plan(tenant_id, plan_id)
        if "databaseNames" in data:
            item.database_names = self._database_names(data["databaseNames"])
        if "name" in data:
            item.name = str(data["name"]).strip()
        if "localTime" in data:
            item.local_time = str(data["localTime"])
        if "timezone" in data:
            item.timezone_name = str(data["timezone"])
        if "enabled" in data:
            item.is_active = bool(data["enabled"])
        if "destinationProfileId" in data:
            item.destination_profile_id = data["destinationProfileId"] or None

        agent = await self._agent(item.tenant_id, str(item.agent_id))
        self._validate_profiles(agent, item.sql_profile_id, item.destination_profile_id)
        next_run = next_run_for_plan(item.local_time, item.timezone_name)
        item.next_run_at = next_run if item.is_active else None
        remove_agent_backup_plan(str(item.id))
        if item.is_active:
            register_agent_backup_plan(item)
        return serialize_agent_backup_plan(item)

    async def delete(self, tenant_id: str, plan_id: str) -> None:
        item = await self._plan(tenant_id, plan_id)
        remove_agent_backup_plan(str(item.id))
        await self.db.delete(item)

    async def _plan(self, tenant_id: str, plan_id: str) -> AgentBackupPlan:
        try:
            parsed = uuid.UUID(plan_id)
        except ValueError as exc:
            raise NotFoundError("Plan de backup") from exc
        item = await self.db.scalar(
            select(AgentBackupPlan).where(
                AgentBackupPlan.id == parsed,
                AgentBackupPlan.tenant_id == tenant_uuid(tenant_id),
            )
        )
        if not item:
            raise NotFoundError("Plan de backup")
        return item

    async def _agent(self, tenant_id_value: uuid.UUID, agent_id: str) -> RemoteAgent:
        try:
            parsed = uuid.UUID(agent_id)
        except ValueError as exc:
            raise NotFoundError("Agente") from exc
        agent = await self.db.scalar(
            select(RemoteAgent).where(
                RemoteAgent.id == parsed,
                RemoteAgent.tenant_id == tenant_id_value,
            )
        )
        if not agent or agent.revoked_at is not None or agent.status == "revoked":
            raise NotFoundError("Agente")
        return agent

    @staticmethod
    def _database_names(values: list[str]) -> list[str]:
        names = list(dict.fromkeys(str(value).strip() for value in values))
        if not names or len(names) > 5000 or any(not _DATABASE_NAME.fullmatch(name) for name in names):
            raise DomainError(
                "INVALID_DATABASE_SELECTION",
                "Seleccione entre 1 y 5000 bases de datos validas",
                422,
            )
        return names

    @staticmethod
    def _validate_profiles(
        agent: RemoteAgent,
        sql_profile_id: str,
        destination_profile_id: str | None,
    ) -> None:
        metadata = agent.metadata_json or {}
        AgentBackupService._require_profile(metadata, "sqlInstances", sql_profile_id)
        if destination_profile_id:
            AgentBackupService._require_profile(
                metadata, "backupDestinations", destination_profile_id
            )


async def run_agent_backup_plan(plan_id: str) -> None:
    async with AsyncSessionLocal() as db:
        item = await db.scalar(
            select(AgentBackupPlan)
            .where(AgentBackupPlan.id == uuid.UUID(plan_id))
            .with_for_update(skip_locked=True)
        )
        if not item or not item.is_active:
            return
        now = datetime.now(timezone.utc)
        if item.last_run_at and now - item.last_run_at < timedelta(minutes=2):
            return
        local_now = now.astimezone(_timezone(item.timezone_name))
        backup_type = backup_type_for_weekday(local_now.weekday())
        if backup_type is None:
            return

        names = list(item.database_names or [])
        service = AgentBackupService(db)
        for start in range(0, len(names), DATABASE_BATCH_SIZE):
            await service.start_backup(
                str(item.tenant_id),
                str(item.agent_id),
                sql_profile_id=item.sql_profile_id,
                database_names=names[start : start + DATABASE_BATCH_SIZE],
                backup_type=backup_type,
                destination_profile_id=item.destination_profile_id,
                command_ttl_seconds=24 * 60 * 60,
            )
        item.last_run_at = now
        job = scheduler.get_job(f"agent-backup-plan:{item.id}")
        item.next_run_at = job.next_run_time if job else next_run_for_plan(
            item.local_time, item.timezone_name, now
        )
        await db.commit()


def register_agent_backup_plan(item: AgentBackupPlan) -> None:
    scheduler.add_job(
        run_agent_backup_plan,
        trigger_for_plan(item.local_time, item.timezone_name),
        args=[str(item.id)],
        id=f"agent-backup-plan:{item.id}",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )


def remove_agent_backup_plan(plan_id: str) -> None:
    job = scheduler.get_job(f"agent-backup-plan:{plan_id}")
    if job:
        scheduler.remove_job(job.id)


async def load_agent_backup_plans() -> None:
    async with AsyncSessionLocal() as db:
        items = (
            await db.execute(
                select(AgentBackupPlan).where(AgentBackupPlan.is_active.is_(True))
            )
        ).scalars()
        for item in items:
            register_agent_backup_plan(item)
