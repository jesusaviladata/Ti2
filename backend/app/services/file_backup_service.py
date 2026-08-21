from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models.file_backup import (
    FileBackupArtifact,
    FileBackupFilter,
    FileBackupSource,
    FileBackupTask,
)
from app.repositories.agent_profile_repository import AgentProfileRepository
from app.repositories.agent_repository import AgentRepository
from app.repositories.cleanup_repository import tenant_uuid
from app.repositories.file_backup_repository import FileBackupRepository
from app.schemas.file_backup import FileBackupTaskCreate, FileBackupTaskUpdate


FILE_BACKUP_CAPABILITY = "file_backup_v1"


def _value(item: Any) -> Any:
    return item.value if isinstance(item, enum.Enum) else item


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _has_file_backup_capability(metadata: dict | None) -> bool:
    capabilities = (metadata or {}).get("capabilities") or []
    if isinstance(capabilities, dict):
        return bool(capabilities.get(FILE_BACKUP_CAPABILITY))
    return FILE_BACKUP_CAPABILITY in capabilities


class FileBackupService:
    def __init__(
        self,
        db: Any,
        *,
        repository: Any | None = None,
        agents: Any | None = None,
        profiles: Any | None = None,
    ):
        self.db = db
        self.repository = repository or FileBackupRepository(db)
        self.agents = agents or AgentRepository(db)
        self.profiles = profiles or AgentProfileRepository(db)

    async def list(
        self,
        tenant_id: str,
        *,
        page: int,
        page_size: int,
        agent_id: uuid.UUID | None,
        active: bool | None,
        search: str | None,
    ) -> dict[str, Any]:
        tasks, total = await self.repository.list_tasks(
            tenant_id,
            skip=(page - 1) * page_size,
            limit=page_size,
            agent_id=agent_id,
            active=active,
            search=search,
        )
        source_map, filter_map = await self.repository.components(
            tenant_id, [task.id for task in tasks]
        )
        return {
            "items": [
                self._serialize(
                    task,
                    source_map.get(task.id, []),
                    filter_map.get(task.id, []),
                )
                for task in tasks
            ],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    async def get(self, tenant_id: str, task_id: str | uuid.UUID) -> dict[str, Any]:
        task = await self._task(tenant_id, task_id)
        source_map, filter_map = await self.repository.components(tenant_id, [task.id])
        return self._serialize(
            task, source_map.get(task.id, []), filter_map.get(task.id, [])
        )

    async def create(
        self, tenant_id: str, body: FileBackupTaskCreate
    ) -> dict[str, Any]:
        agent = await self._agent(tenant_id, body.agent_id)
        await self._destination(tenant_id, agent.id, body.destination_profile_id)
        now = datetime.now(timezone.utc)
        task = FileBackupTask(
            id=uuid.uuid4(),
            tenant_id=tenant_uuid(tenant_id),
            created_at=now,
            updated_at=now,
            name=body.name,
            agent_id=agent.id,
            destination_profile_id=body.destination_profile_id,
            strategy=body.strategy,
            format=body.format,
            schedule=body.schedule.model_dump(by_alias=True),
            timezone_name=body.timezone_name,
            missed_run_policy=body.missed_run_policy,
            retention_full_chains=body.retention_full_chains,
            vss_policy=body.vss_policy,
            verification_mode=body.verification_mode,
            config_revision=1,
            is_active=body.is_active,
        )
        sources = self._sources(task, body.sources, now)
        filters = self._filters(task, body.filters, now)
        self.repository.add_task(task)
        for source in sources:
            self.repository.add_source(source)
        for item in filters:
            self.repository.add_filter(item)
        await self.db.flush()
        return self._serialize(task, sources, filters)

    async def update(
        self,
        tenant_id: str,
        task_id: str | uuid.UUID,
        body: FileBackupTaskUpdate,
    ) -> dict[str, Any]:
        task = await self._task(tenant_id, task_id)
        agent = await self._agent(tenant_id, task.agent_id)
        changes = body.model_dump(exclude_unset=True)
        if "destination_profile_id" in changes:
            await self._destination(
                tenant_id, agent.id, changes["destination_profile_id"]
            )
        now = datetime.now(timezone.utc)
        scalar_fields = (
            "name",
            "destination_profile_id",
            "strategy",
            "format",
            "timezone_name",
            "missed_run_policy",
            "retention_full_chains",
            "vss_policy",
            "verification_mode",
            "is_active",
        )
        for field in scalar_fields:
            if field in changes:
                value = changes[field]
                if field in {"name", "timezone_name"}:
                    value = value.strip()
                setattr(task, field, value)
        if "schedule" in changes:
            task.schedule = body.schedule.model_dump(by_alias=True)
        source_map, filter_map = await self.repository.components(tenant_id, [task.id])
        sources = source_map.get(task.id, [])
        filters = filter_map.get(task.id, [])
        if body.sources is not None:
            sources = self._sources(task, body.sources, now)
            await self.repository.replace_sources(task, sources)
        if body.filters is not None:
            filters = self._filters(task, body.filters, now)
            await self.repository.replace_filters(task, filters)
        task.config_revision += 1
        task.updated_at = now
        await self.db.flush()
        return self._serialize(task, sources, filters)

    async def delete(self, tenant_id: str, task_id: str | uuid.UUID) -> str:
        task = await self._task(tenant_id, task_id)
        if await self.repository.has_history(tenant_id, task.id):
            task.is_active = False
            task.config_revision += 1
            task.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            return "deactivated"
        await self.repository.delete_task(task)
        await self.db.flush()
        return "deleted"

    async def set_artifact_protection(
        self,
        tenant_id: str,
        artifact_id: str | uuid.UUID,
        *,
        protected: bool,
        user_id: str | uuid.UUID,
    ) -> dict[str, Any]:
        artifact: FileBackupArtifact | None = await self.repository.get_artifact(
            tenant_id, artifact_id
        )
        if artifact is None:
            raise NotFoundError("Artefacto")
        artifact.protected = protected
        artifact.protected_at = datetime.now(timezone.utc) if protected else None
        artifact.protected_by = uuid.UUID(str(user_id)) if protected else None
        await self.db.flush()
        return {
            "id": str(artifact.id),
            "protected": artifact.protected,
            "protectedAt": _iso(artifact.protected_at),
            "protectedBy": str(artifact.protected_by) if artifact.protected_by else None,
        }

    async def _task(self, tenant_id: str, task_id: str | uuid.UUID) -> FileBackupTask:
        task = await self.repository.get_task(tenant_id, task_id)
        if task is None:
            raise NotFoundError("Tarea de respaldo")
        return task

    async def _agent(self, tenant_id: str, agent_id: str | uuid.UUID):
        agent = await self.agents.get_agent(tenant_id, str(agent_id))
        if agent is None:
            raise NotFoundError("Agente")
        if agent.status == "revoked" or agent.revoked_at is not None:
            raise ConflictError("El agente está revocado", code="AGENT_REVOKED")
        if not _has_file_backup_capability(agent.metadata_json):
            raise ConflictError(
                "El agente debe actualizarse para respaldar archivos",
                code="AGENT_FILE_BACKUP_UNSUPPORTED",
            )
        return agent

    async def _destination(
        self, tenant_id: str, agent_id: uuid.UUID, profile_id: uuid.UUID
    ):
        profile = await self.profiles.get(
            tenant_id, agent_id, str(profile_id)
        )
        if (
            profile is None
            or profile.agent_id != agent_id
            or profile.profile_type != "destination"
            or not profile.is_active
            or profile.sync_status != "applied"
        ):
            raise DomainError(
                "FILE_BACKUP_DESTINATION_INVALID",
                "El destino debe pertenecer al agente y estar aplicado",
                422,
            )
        return profile

    @staticmethod
    def _sources(task: FileBackupTask, inputs, now: datetime) -> list[FileBackupSource]:
        return [
            FileBackupSource(
                id=uuid.uuid4(),
                tenant_id=task.tenant_id,
                created_at=now,
                task_id=task.id,
                path=item.path,
                include_subfolders=item.include_subfolders,
                position=position,
            )
            for position, item in enumerate(inputs)
        ]

    @staticmethod
    def _filters(task: FileBackupTask, inputs, now: datetime) -> list[FileBackupFilter]:
        return [
            FileBackupFilter(
                id=uuid.uuid4(),
                tenant_id=task.tenant_id,
                created_at=now,
                task_id=task.id,
                kind=item.kind,
                operator=item.operator,
                pattern=item.pattern,
                is_enabled=item.is_enabled,
            )
            for item in inputs
        ]

    @staticmethod
    def _serialize(
        task: FileBackupTask,
        sources: list[FileBackupSource],
        filters: list[FileBackupFilter],
    ) -> dict[str, Any]:
        return {
            "id": str(task.id),
            "tenantId": str(task.tenant_id),
            "name": task.name,
            "agentId": str(task.agent_id),
            "destinationProfileId": str(task.destination_profile_id),
            "sources": [
                {
                    "path": source.path,
                    "includeSubfolders": source.include_subfolders,
                }
                for source in sorted(sources, key=lambda source: source.position)
            ],
            "filters": [
                {
                    "kind": _value(item.kind),
                    "operator": _value(item.operator),
                    "pattern": item.pattern,
                    "isEnabled": item.is_enabled,
                }
                for item in filters
            ],
            "strategy": _value(task.strategy),
            "format": _value(task.format),
            "schedule": task.schedule,
            "timezoneName": task.timezone_name,
            "missedRunPolicy": task.missed_run_policy,
            "retentionFullChains": task.retention_full_chains,
            "vssPolicy": task.vss_policy,
            "verificationMode": task.verification_mode,
            "configRevision": task.config_revision,
            "isActive": task.is_active,
            "firstRunWillBeFull": True,
            "createdAt": _iso(task.created_at),
            "updatedAt": _iso(task.updated_at),
        }
