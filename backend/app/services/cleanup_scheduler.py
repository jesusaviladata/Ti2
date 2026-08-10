from __future__ import annotations

import uuid
from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.scheduler import scheduler
from app.models.operations import CleanupSchedule
from app.models.user import User, UserRole


def next_run_for_cron(
    expression: str, now: datetime | None = None
) -> datetime | None:
    trigger = CronTrigger.from_crontab(expression, timezone="UTC")
    return trigger.get_next_fire_time(None, now or datetime.now(timezone.utc))


async def run_cleanup_schedule(schedule_id: str) -> None:
    from app.services.cleanup_service import CleanupService

    async with AsyncSessionLocal() as db:
        schedule = (
            await db.execute(
                select(CleanupSchedule).where(
                    CleanupSchedule.id == uuid.UUID(schedule_id)
                )
            )
        ).scalar_one_or_none()
        if not schedule or not schedule.enabled:
            return
        operator = (
            await db.execute(
                select(User)
                .where(
                    User.tenant_id == schedule.tenant_id,
                    User.is_active.is_(True),
                    User.role.in_(
                        [
                            UserRole.admin,
                            UserRole.supervisor,
                            UserRole.technician,
                        ]
                    ),
                )
                .order_by(User.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()
        if not operator:
            return
        service = CleanupService(db)
        simulation = await service.scan(
            str(schedule.tenant_id),
            str(operator.id),
            str(schedule.folder_id),
        )
        if simulation["files"]:
            await service.execute(
                str(schedule.tenant_id),
                str(operator.id),
                [item["path"] for item in simulation["files"]],
                simulation["simulationId"],
            )
        schedule.last_run_at = datetime.now(timezone.utc)
        job = scheduler.get_job(f"cleanup:{schedule.id}")
        schedule.next_run_at = job.next_run_time if job else None
        await db.commit()


def register_cleanup_schedule(item: CleanupSchedule) -> None:
    scheduler.add_job(
        run_cleanup_schedule,
        CronTrigger.from_crontab(item.cron_expression, timezone="UTC"),
        args=[str(item.id)],
        id=f"cleanup:{item.id}",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )


def remove_cleanup_schedule(schedule_id: str) -> None:
    job = scheduler.get_job(f"cleanup:{schedule_id}")
    if job:
        scheduler.remove_job(job.id)


async def load_cleanup_schedules() -> None:
    async with AsyncSessionLocal() as db:
        items = (
            await db.execute(
                select(CleanupSchedule).where(
                    CleanupSchedule.enabled.is_(True)
                )
            )
        ).scalars()
        for item in items:
            register_cleanup_schedule(item)
