from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models.backup import Backup, BackupDestination, BackupStatus, BackupType
from app.models.operations import BackgroundJob
from app.repositories.agent_repository import AgentRepository
from app.repositories.cleanup_repository import tenant_uuid
from app.services.agent_command_service import AgentCommandService
from app.services.backup_origin import create_backup_origin_snapshot


class AgentBackupService:
    def __init__(
        self,
        db: Any,
        *,
        agent_repo: AgentRepository | Any | None = None,
        command_service: AgentCommandService | Any | None = None,
    ):
        self.db = db
        self.agents = agent_repo or AgentRepository(db)
        self.commands = command_service or AgentCommandService(db)

    async def list_agents(self, tenant_id: str) -> list[dict[str, Any]]:
        items = await self.agents.list_agents(tenant_id)
        return [
            {
                "id": str(item.id),
                "hostname": item.hostname,
                "status": item.status,
                "lastSeenAt": item.last_seen_at.isoformat() if item.last_seen_at else None,
                "sqlInstances": (item.metadata_json or {}).get("sqlInstances", []),
                "backupDestinations": (item.metadata_json or {}).get("backupDestinations", []),
            }
            for item in items
            if item.status != "revoked" and item.revoked_at is None
        ]

    async def start_database_list(
        self, tenant_id: str, agent_id: str, sql_profile_id: str
    ) -> BackgroundJob:
        agent = await self._active_agent(tenant_id, agent_id)
        self._require_profile(agent.metadata_json, "sqlInstances", sql_profile_id)
        job = BackgroundJob(
            tenant_id=agent.tenant_id,
            kind="agent_sql_databases",
            status="queued",
            phase="queued",
            resource_id=agent.id,
        )
        self.db.add(job)
        await self.db.flush()
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=agent_id,
            command_type="list_sql_databases",
            payload={"sqlProfileId": sql_profile_id},
            idempotency_key=f"sql-databases:{job.id}",
            job_id=str(job.id),
        )
        return job

    async def start_backup(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        sql_profile_id: str,
        database_names: list[str],
        backup_type: str,
        destination_profile_id: str | None,
        command_ttl_seconds: int | None = None,
    ) -> tuple[BackgroundJob, list[Backup]]:
        agent = await self._active_agent(tenant_id, agent_id)
        self._require_profile(agent.metadata_json, "sqlInstances", sql_profile_id)
        if destination_profile_id:
            self._require_profile(
                agent.metadata_json, "backupDestinations", destination_profile_id
            )
        names = list(dict.fromkeys(name.strip() for name in database_names if name.strip()))
        if not names:
            raise DomainError("DATABASE_REQUIRED", "Seleccione al menos una base de datos", 422)
        if len(names) > 100:
            raise DomainError(
                "TOO_MANY_DATABASES", "Seleccione un maximo de 100 bases de datos", 422
            )
        destination = (
            BackupDestination.secondary_server
            if destination_profile_id
            else BackupDestination.local
        )
        run_id = str(uuid.uuid4())
        origin = create_backup_origin_snapshot(
            agent,
            sql_profile_id=sql_profile_id,
            destination_profile_id=destination_profile_id,
        )
        records: list[Backup] = []
        for name in names:
            record = Backup(
                tenant_id=tenant_uuid(tenant_id),
                database_name=name,
                backup_type=BackupType(backup_type),
                status=BackupStatus.pending,
                destination=destination,
                agent_id=agent.id,
                run_id=run_id,
                phase="queued",
                progress_percent=0,
                delivery_status="pending",
                delivery_profile_id=destination_profile_id,
                started_at=datetime.now(timezone.utc),
                origin_snapshot=origin,
            )
            self.db.add(record)
            records.append(record)
        await self.db.flush()
        job = BackgroundJob(
            tenant_id=agent.tenant_id,
            kind="agent_backup",
            status="queued",
            phase="queued",
            resource_id=agent.id,
            total_units=len(records),
            result={"backupRecordIds": [str(item.id) for item in records]},
        )
        self.db.add(job)
        await self.db.flush()
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=agent_id,
            command_type="run_backup_batch",
            payload={
                "runId": run_id,
                "sqlProfileId": sql_profile_id,
                "databaseNames": names,
                "backupType": backup_type,
                "destinationProfileId": destination_profile_id,
                "backupRecordIds": [str(item.id) for item in records],
                "origin": origin,
            },
            idempotency_key=f"backup:{job.id}",
            job_id=str(job.id),
            ttl_seconds=command_ttl_seconds,
        )
        return job, records

    async def _active_agent(self, tenant_id: str, agent_id: str):
        agent = await self.agents.get_agent(tenant_id, agent_id)
        if agent is None:
            raise NotFoundError("Agente")
        if agent.status == "revoked" or agent.revoked_at is not None:
            raise ConflictError("El agente esta revocado", code="AGENT_REVOKED")
        return agent

    @staticmethod
    def _require_profile(metadata: dict, field: str, profile_id: str) -> None:
        if not any(str(item.get("id")) == profile_id for item in (metadata or {}).get(field, [])):
            raise DomainError(
                "AGENT_PROFILE_NOT_FOUND",
                "El perfil seleccionado no esta configurado en el agente",
                422,
            )
