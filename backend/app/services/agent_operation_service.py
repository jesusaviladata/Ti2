from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models.backup import Backup, BackupDestination, BackupStatus, BackupType
from app.models.operations import AgentCommand, BackgroundJob, RemoteAgent, RemoteCleanupExecution, RemoteServer
from app.repositories.agent_admin_repository import AgentAdminRepository
from app.repositories.agent_repository import AgentRepository
from app.repositories.cleanup_repository import tenant_uuid
from app.services.agent_command_service import AgentCommandService


FIXED_TARGET_FOLDERS = ["Log", "LogSec", "LogsRadian", "Respuesta"]
FIXED_TARGET_FILES = ["BD_log.txt"]


class AgentOperationService:
    def __init__(self, db: Any):
        self.db = db
        self.agents = AgentRepository(db)
        self.admin = AgentAdminRepository(db)
        self.commands = AgentCommandService(db)

    async def profiles(self, tenant_id: str, agent_id: str) -> dict[str, Any]:
        agent = await self._agent(tenant_id, agent_id, require_online=False)
        metadata = agent.metadata_json or {}
        return {
            "agentId": str(agent.id),
            "sqlInstances": list(metadata.get("sqlInstances") or []),
            "backupDestinations": list(metadata.get("backupDestinations") or []),
        }

    async def start_database_catalog(
        self, tenant_id: str, agent_id: str, sql_profile_id: str
    ) -> BackgroundJob:
        agent = await self._agent(tenant_id, agent_id)
        self._require_profile(agent, "sqlInstances", sql_profile_id)
        job = self._job(agent, "agent_database_catalog", agent.id)
        await self.db.flush()
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=agent_id,
            command_type="list_sql_databases",
            payload={"sqlProfileId": sql_profile_id},
            idempotency_key=f"database-catalog:{job.id}",
            job_id=str(job.id),
        )
        return job

    async def start_backup_run(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        sql_profile_id: str,
        database_names: list[str],
        backup_type: str,
        destination_profile_id: str | None,
        trigger_reason: str | None = None,
    ) -> tuple[BackgroundJob, list[Backup]]:
        agent = await self._agent(tenant_id, agent_id)
        self._require_profile(agent, "sqlInstances", sql_profile_id)
        if destination_profile_id:
            self._require_profile(agent, "backupDestinations", destination_profile_id)
        names = list(dict.fromkeys(name.strip() for name in database_names if name.strip()))
        if not names or len(names) > 100:
            raise DomainError(
                "BACKUP_DATABASE_SELECTION_INVALID",
                "Seleccione entre 1 y 100 bases de datos",
                422,
            )
        try:
            parsed_type = BackupType(backup_type)
        except ValueError:
            raise DomainError("BACKUP_TYPE_INVALID", "El tipo de backup no es válido", 422) from None
        if parsed_type not in {BackupType.full, BackupType.differential, BackupType.log}:
            raise DomainError("BACKUP_TYPE_INVALID", "El tipo de backup no es válido", 422)

        run_id = str(uuid.uuid4())
        job = self._job(agent, "agent_backup", agent.id)
        destination = BackupDestination.nas if destination_profile_id else BackupDestination.local
        records = [
            Backup(
                tenant_id=tenant_uuid(tenant_id),
                database_name=name,
                backup_type=parsed_type,
                status=BackupStatus.pending,
                destination=destination,
                agent_id=agent.id,
                run_id=run_id,
                phase="queued",
                progress_percent=0,
                trigger_reason=trigger_reason,
                delivery_status="pending",
                delivery_profile_id=destination_profile_id,
            )
            for name in names
        ]
        self.db.add_all(records)
        await self.db.flush()
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=agent_id,
            command_type="run_backup_batch",
            payload={
                "runId": run_id,
                "sqlProfileId": sql_profile_id,
                "databaseNames": names,
                "backupType": parsed_type.value,
                "destinationProfileId": destination_profile_id,
                "backupIds": {item.database_name: str(item.id) for item in records},
            },
            idempotency_key=f"backup-run:{run_id}",
            job_id=str(job.id),
        )
        return job, records

    async def start_cleanup_simulation(
        self, tenant_id: str, agent_id: str
    ) -> BackgroundJob:
        agent = await self._agent(tenant_id, agent_id)
        server = await self._configured_server(tenant_id, agent_id)
        job = self._job(agent, "agent_cleanup_simulation", server.id)
        await self.db.flush()
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=agent_id,
            command_type="simulate_structural_cleanup",
            payload={
                "root": server.base_path,
                "containerFolder": "core",
                "targetFolders": FIXED_TARGET_FOLDERS,
                "targetFiles": FIXED_TARGET_FILES,
                "configurationHash": server.configuration_hash,
            },
            idempotency_key=f"cleanup-simulation:{job.id}",
            job_id=str(job.id),
        )
        return job

    async def retry_backup_delivery(
        self, tenant_id: str, backup_id: str
    ) -> BackgroundJob:
        try:
            parsed_id = uuid.UUID(backup_id)
        except ValueError:
            raise NotFoundError("Backup") from None
        backup = (
            await self.db.execute(
                select(Backup).where(
                    Backup.id == parsed_id,
                    Backup.tenant_id == tenant_uuid(tenant_id),
                )
            )
        ).scalar_one_or_none()
        if backup is None:
            raise NotFoundError("Backup")
        if (
            backup.status != BackupStatus.completed
            or backup.delivery_status != "failed"
            or not backup.agent_id
            or not backup.run_id
            or not backup.archive_path
            or not backup.archive_sha256
            or not backup.delivery_profile_id
        ):
            raise ConflictError(
                "La entrega de este backup no se puede reintentar",
                code="BACKUP_DELIVERY_RETRY_NOT_AVAILABLE",
            )
        agent = await self._agent(tenant_id, str(backup.agent_id))
        self._require_profile(agent, "backupDestinations", backup.delivery_profile_id)
        original = await self.db.execute(
            select(Backup).where(
                Backup.tenant_id == backup.tenant_id,
                Backup.run_id == backup.run_id,
            )
        )
        run_backups = list(original.scalars().all())
        sql_profile_id = ""
        commands = await self.db.execute(
            select(AgentCommand).where(
                AgentCommand.tenant_id == backup.tenant_id,
                AgentCommand.agent_id == backup.agent_id,
                AgentCommand.command_type == "run_backup_batch",
            ).order_by(AgentCommand.created_at.desc())
        )
        for command in commands.scalars().all():
            if str(command.payload.get("runId") or "") == backup.run_id:
                sql_profile_id = str(command.payload.get("sqlProfileId") or "")
                break
        if not sql_profile_id:
            raise ConflictError(
                "No se encontró el perfil SQL original",
                code="BACKUP_DELIVERY_CONTEXT_MISSING",
            )
        job = self._job(agent, "agent_backup_delivery_retry", agent.id)
        await self.db.flush()
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=str(agent.id),
            command_type="retry_backup_delivery",
            payload={
                "runId": backup.run_id,
                "sqlProfileId": sql_profile_id,
                "destinationProfileId": backup.delivery_profile_id,
                "zipPath": backup.archive_path,
                "zipSha256": backup.archive_sha256,
                "backupIds": {item.database_name: str(item.id) for item in run_backups},
            },
            idempotency_key=f"backup-delivery-retry:{job.id}",
            job_id=str(job.id),
        )
        for item in run_backups:
            item.delivery_status = "processing"
            item.delivery_phase = "queued"
            item.delivery_progress = 0
            item.delivery_error_message = None
        return job

    async def start_cleanup_execution(
        self, tenant_id: str, simulation_job_id: str, user_id: str | None = None
    ) -> BackgroundJob:
        simulation = await self.admin.get_job(tenant_id, simulation_job_id)
        if simulation is None or simulation.kind != "agent_cleanup_simulation":
            raise NotFoundError("Simulación")
        if simulation.status != "completed" or not simulation.result:
            raise ConflictError(
                "La simulación todavía no está lista", code="CLEANUP_SIMULATION_NOT_READY"
            )
        result = simulation.result
        if not result.get("simulationId") or not result.get("manifestHash"):
            raise ConflictError(
                "La simulación no contiene un manifiesto válido",
                code="CLEANUP_SIMULATION_INVALID",
            )
        server = await self.admin.get_server(tenant_id, str(simulation.resource_id))
        if server is None or server.agent_id is None:
            raise NotFoundError("Configuración del agente")
        simulation_command = await self.admin.get_command_for_job(simulation.id)
        if (
            simulation_command is None
            or simulation_command.payload.get("configurationHash")
            != server.configuration_hash
        ):
            raise ConflictError(
                "La configuración cambió; ejecute una nueva simulación",
                code="CLEANUP_SIMULATION_STALE",
            )
        agent = await self._agent(tenant_id, str(server.agent_id))
        execution = RemoteCleanupExecution(
            tenant_id=agent.tenant_id,
            server_id=server.id,
            user_id=uuid.UUID(user_id) if user_id else None,
            kind="agent_manual",
            status="running",
            targets=[
                "core/Log",
                "core/LogSec",
                "core/LogsRadian",
                "core/Respuesta",
                "core/BD_log.txt",
            ],
            summary={"simulationJobId": simulation_job_id, "root": server.base_path},
        )
        self.db.add(execution)
        await self.db.flush()
        job = self._job(agent, "agent_cleanup_execution", execution.id)
        await self.db.flush()
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=str(agent.id),
            command_type="execute_structural_direct",
            payload={
                "simulationId": result["simulationId"],
                "manifestHash": result["manifestHash"],
            },
            idempotency_key=f"cleanup-execution:{simulation.id}",
            job_id=str(job.id),
        )
        return job

    async def _agent(
        self, tenant_id: str, agent_id: str, *, require_online: bool = True
    ) -> RemoteAgent:
        agent = await self.agents.get_agent(tenant_id, agent_id)
        if agent is None:
            raise NotFoundError("Agente")
        if agent.status == "revoked" or agent.revoked_at is not None:
            raise ConflictError("El agente está revocado", code="AGENT_REVOKED")
        if require_online and not _is_online(agent):
            raise ConflictError("El agente está desconectado", code="AGENT_OFFLINE")
        return agent

    async def _configured_server(self, tenant_id: str, agent_id: str) -> RemoteServer:
        server = await self.admin.get_server_for_agent(tenant_id, agent_id)
        if server is None or not server.base_path or not server.validated_at:
            raise ConflictError(
                "Configure y valide la raíz del agente antes de limpiar",
                code="AGENT_ROOT_REQUIRED",
            )
        return server

    @staticmethod
    def _require_profile(agent: RemoteAgent, key: str, profile_id: str) -> None:
        profiles = list((agent.metadata_json or {}).get(key) or [])
        if not any(str(item.get("id")) == profile_id for item in profiles):
            raise ConflictError(
                "El perfil seleccionado no está disponible en el agente",
                code="AGENT_PROFILE_NOT_AVAILABLE",
            )

    def _job(self, agent: RemoteAgent, kind: str, resource_id: uuid.UUID) -> BackgroundJob:
        job = BackgroundJob(
            tenant_id=agent.tenant_id,
            kind=kind,
            status="queued",
            phase="queued",
            resource_id=resource_id,
        )
        self.db.add(job)
        return job


def _is_online(agent: RemoteAgent, *, now: datetime | None = None) -> bool:
    if agent.status == "revoked" or agent.revoked_at is not None or agent.last_seen_at is None:
        return False
    current = now or datetime.now(timezone.utc)
    seen = agent.last_seen_at
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return (current - seen).total_seconds() <= 180
