from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file_backup import (
    FileBackupArtifact,
    FileBackupChain,
    FileBackupFilter,
    FileBackupRun,
    FileBackupSource,
    FileBackupTask,
)
from app.models.operations import BackgroundJob
from app.repositories.cleanup_repository import tenant_uuid


class FileBackupRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_tasks(
        self,
        tenant_id: str,
        *,
        skip: int,
        limit: int,
        agent_id: uuid.UUID | None,
        active: bool | None,
        search: str | None,
    ) -> tuple[list[FileBackupTask], int]:
        conditions = [FileBackupTask.tenant_id == tenant_uuid(tenant_id)]
        if agent_id is not None:
            conditions.append(FileBackupTask.agent_id == agent_id)
        if active is not None:
            conditions.append(FileBackupTask.is_active.is_(active))
        if search and search.strip():
            conditions.append(FileBackupTask.name.ilike(f"%{search.strip()}%"))

        items = (
            await self.db.execute(
                select(FileBackupTask)
                .where(*conditions)
                .order_by(FileBackupTask.name, FileBackupTask.created_at)
                .offset(skip)
                .limit(limit)
            )
        ).scalars().all()
        total = (
            await self.db.execute(
                select(func.count()).select_from(FileBackupTask).where(*conditions)
            )
        ).scalar_one()
        return list(items), int(total)

    async def get_task(self, tenant_id: str, task_id: str | uuid.UUID):
        try:
            parsed = uuid.UUID(str(task_id))
        except ValueError:
            return None
        result = await self.db.execute(
            select(FileBackupTask).where(
                FileBackupTask.id == parsed,
                FileBackupTask.tenant_id == tenant_uuid(tenant_id),
            )
        )
        return result.scalar_one_or_none()

    def add_task(self, task: FileBackupTask) -> None:
        self.db.add(task)

    def add_source(self, source: FileBackupSource) -> None:
        self.db.add(source)

    def add_filter(self, item: FileBackupFilter) -> None:
        self.db.add(item)

    async def components(
        self, tenant_id: str, task_ids: list[uuid.UUID]
    ) -> tuple[dict[uuid.UUID, list[FileBackupSource]], dict[uuid.UUID, list[FileBackupFilter]]]:
        if not task_ids:
            return {}, {}
        tenant = tenant_uuid(tenant_id)
        sources = (
            await self.db.execute(
                select(FileBackupSource)
                .where(
                    FileBackupSource.tenant_id == tenant,
                    FileBackupSource.task_id.in_(task_ids),
                )
                .order_by(FileBackupSource.task_id, FileBackupSource.position)
            )
        ).scalars().all()
        filters = (
            await self.db.execute(
                select(FileBackupFilter)
                .where(
                    FileBackupFilter.tenant_id == tenant,
                    FileBackupFilter.task_id.in_(task_ids),
                )
                .order_by(FileBackupFilter.task_id, FileBackupFilter.created_at)
            )
        ).scalars().all()
        source_map: dict[uuid.UUID, list[FileBackupSource]] = {}
        filter_map: dict[uuid.UUID, list[FileBackupFilter]] = {}
        for item in sources:
            source_map.setdefault(item.task_id, []).append(item)
        for item in filters:
            filter_map.setdefault(item.task_id, []).append(item)
        return source_map, filter_map

    async def replace_sources(
        self, task: FileBackupTask, sources: list[FileBackupSource]
    ) -> None:
        await self.db.execute(
            delete(FileBackupSource).where(
                FileBackupSource.tenant_id == task.tenant_id,
                FileBackupSource.task_id == task.id,
            )
        )
        for source in sources:
            self.db.add(source)

    async def replace_filters(
        self, task: FileBackupTask, filters: list[FileBackupFilter]
    ) -> None:
        await self.db.execute(
            delete(FileBackupFilter).where(
                FileBackupFilter.tenant_id == task.tenant_id,
                FileBackupFilter.task_id == task.id,
            )
        )
        for item in filters:
            self.db.add(item)

    async def has_history(self, tenant_id: str, task_id: uuid.UUID) -> bool:
        count = (
            await self.db.execute(
                select(func.count())
                .select_from(FileBackupRun)
                .where(
                    FileBackupRun.tenant_id == tenant_uuid(tenant_id),
                    FileBackupRun.task_id == task_id,
                )
            )
        ).scalar_one()
        return bool(count)

    async def delete_task(self, task: FileBackupTask) -> None:
        await self.db.delete(task)

    async def get_artifact(
        self, tenant_id: str, artifact_id: str | uuid.UUID
    ) -> FileBackupArtifact | None:
        try:
            parsed = uuid.UUID(str(artifact_id))
        except ValueError:
            return None
        result = await self.db.execute(
            select(FileBackupArtifact).where(
                FileBackupArtifact.id == parsed,
                FileBackupArtifact.tenant_id == tenant_uuid(tenant_id),
            )
        )
        return result.scalar_one_or_none()

    async def list_runs(
        self, tenant_id: str, task_id: uuid.UUID, *, skip: int, limit: int
    ) -> tuple[list[FileBackupRun], int]:
        conditions = (
            FileBackupRun.tenant_id == tenant_uuid(tenant_id),
            FileBackupRun.task_id == task_id,
        )
        items = (
            await self.db.execute(
                select(FileBackupRun)
                .where(*conditions)
                .order_by(FileBackupRun.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
        ).scalars().all()
        total = (
            await self.db.execute(
                select(func.count()).select_from(FileBackupRun).where(*conditions)
            )
        ).scalar_one()
        return list(items), int(total)

    async def get_run(self, tenant_id: str, run_id: str | uuid.UUID):
        try:
            parsed = uuid.UUID(str(run_id))
        except ValueError:
            return None
        return (
            await self.db.execute(
                select(FileBackupRun).where(
                    FileBackupRun.tenant_id == tenant_uuid(tenant_id),
                    FileBackupRun.id == parsed,
                )
            )
        ).scalar_one_or_none()

    async def latest_completed_run(self, tenant_id: str, task_id: uuid.UUID):
        return (
            await self.db.execute(
                select(FileBackupRun)
                .where(
                    FileBackupRun.tenant_id == tenant_uuid(tenant_id),
                    FileBackupRun.task_id == task_id,
                    FileBackupRun.status.in_(("completed", "completed_with_warnings")),
                )
                .order_by(FileBackupRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def active_run(self, tenant_id: str, task_id: uuid.UUID):
        return (
            await self.db.execute(
                select(FileBackupRun)
                .where(
                    FileBackupRun.tenant_id == tenant_uuid(tenant_id),
                    FileBackupRun.task_id == task_id,
                    FileBackupRun.status.in_(("queued", "preflight", "running")),
                )
                .order_by(FileBackupRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def get_chain(self, tenant_id: str, chain_id: str | uuid.UUID):
        try:
            parsed = uuid.UUID(str(chain_id))
        except ValueError:
            return None
        return (
            await self.db.execute(
                select(FileBackupChain).where(
                    FileBackupChain.tenant_id == tenant_uuid(tenant_id),
                    FileBackupChain.id == parsed,
                )
            )
        ).scalar_one_or_none()

    async def get_simulation(self, tenant_id: str, simulation_id: str | uuid.UUID):
        try:
            parsed = uuid.UUID(str(simulation_id))
        except ValueError:
            return None
        return (
            await self.db.execute(
                select(BackgroundJob).where(
                    BackgroundJob.tenant_id == tenant_uuid(tenant_id),
                    BackgroundJob.id == parsed,
                    BackgroundJob.kind == "agent_simulate_file_backup",
                )
            )
        ).scalar_one_or_none()

    async def active_job_for_run(self, tenant_id: str, run_id: uuid.UUID):
        return (
            await self.db.execute(
                select(BackgroundJob)
                .where(
                    BackgroundJob.tenant_id == tenant_uuid(tenant_id),
                    BackgroundJob.resource_id == run_id,
                    BackgroundJob.kind.in_(("agent_run_file_backup", "agent_resume_file_backup")),
                    BackgroundJob.status.in_(("queued", "running")),
                )
                .order_by(BackgroundJob.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
