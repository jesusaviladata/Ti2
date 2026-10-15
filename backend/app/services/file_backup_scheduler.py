"""Persistent due-slot dispatch for file tasks; transactions prevent duplicate runs."""
from datetime import datetime, timedelta, timezone
import logging
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.scheduler import scheduler
from app.models.file_backup import FileBackupRun, FileBackupTask
from app.schemas.file_backup import FileBackupRunCreate
from app.services.file_backup_service import FileBackupService

logger = logging.getLogger(__name__)


def due_slot(schedule: dict, timezone_name: str, created_at: datetime, now: datetime):
    zone = ZoneInfo(timezone_name)
    local_now = now.astimezone(zone)
    hour, minute = map(int, schedule['localTime'].split(':'))
    weekdays = schedule['weekdays']
    created = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at
    for offset in range(8):
        day = local_now.date() - timedelta(days=offset)
        if day.weekday() not in weekdays:
            continue
        slot = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone).astimezone(timezone.utc)
        if created <= slot <= now:
            return slot
    return None


async def dispatch_file_backups():
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        ids = list((await db.execute(select(FileBackupTask.id).where(FileBackupTask.is_active.is_(True)))).scalars())
    for task_id in ids:
        try:
            async with AsyncSessionLocal() as db:
                task = (await db.execute(select(FileBackupTask).where(FileBackupTask.id == task_id).with_for_update(skip_locked=True))).scalar_one_or_none()
                if task is None or not task.is_active:
                    continue
                slot = due_slot(task.schedule, task.timezone_name, task.created_at, now)
                if slot is None or (task.missed_run_policy == 'skip' and (now - slot).total_seconds() >= 60):
                    continue
                slot_key = slot.isoformat()
                previous = (await db.execute(select(FileBackupRun.id).where(
                    FileBackupRun.tenant_id == task.tenant_id,
                    FileBackupRun.task_id == task.id,
                    FileBackupRun.summary['scheduledFor'].astext == slot_key,
                ).limit(1))).scalar_one_or_none()
                if previous is not None:
                    continue
                service = FileBackupService(db)
                if await service.repository.active_run(str(task.tenant_id), task.id) is not None:
                    continue
                result = await service.create_run(str(task.tenant_id), task.id, FileBackupRunCreate())
                run = await service.repository.get_run(str(task.tenant_id), result['id'])
                run.summary = {**(run.summary or {}), 'trigger': 'scheduled', 'scheduledFor': slot_key}
                await db.commit()
        except Exception:
            # Keep the slot unclaimed so run_once can retry after reconnection.
            logger.exception('No se pudo programar la tarea de archivos %s', task_id)


def register_file_backup_scheduler():
    scheduler.add_job(dispatch_file_backups, 'interval', seconds=30,
                      id='file-backup-dispatch', replace_existing=True,
                      coalesce=True, max_instances=1, misfire_grace_time=60)
