from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.errors import ConflictError, NotFoundError
from app.models.operations import BackgroundJob, RemoteAgent, RemoteServer
from app.repositories.agent_admin_repository import AgentAdminRepository
from app.repositories.agent_repository import AgentRepository
from app.repositories.cleanup_repository import tenant_uuid
from app.services.agent_command_service import AgentCommandService, canonical_json


DEFAULT_TARGET_FOLDERS = ["Log", "LogSec", "LogsRadian", "Respuesta"]
DEFAULT_TARGET_FILES = ["BD_log.txt"]


def configuration_hash(
    agent_id: str,
    root: str,
    target_folders: list[str],
    target_files: list[str],
) -> str:
    body = canonical_json(
        {
            "agentId": agent_id,
            "root": root.strip(),
            "targetFiles": target_files,
            "targetFolders": target_folders,
        }
    )
    return hashlib.sha256(body).hexdigest()


class AgentAdminService:
    def __init__(
        self,
        db: Any,
        *,
        agent_repo: AgentRepository | Any | None = None,
        admin_repo: AgentAdminRepository | Any | None = None,
        command_service: AgentCommandService | Any | None = None,
    ):
        self.db = db
        self.agent_repo = agent_repo or AgentRepository(db)
        self.admin_repo = admin_repo or AgentAdminRepository(db)
        self.commands = command_service or AgentCommandService(db)

    async def start_browse(
        self, tenant_id: str, agent_id: str, path: str | None
    ) -> BackgroundJob:
        agent = await self._active_agent(tenant_id, agent_id)
        job = BackgroundJob(
            tenant_id=agent.tenant_id,
            kind="agent_browse",
            status="queued",
            phase="queued",
            resource_id=agent.id,
        )
        self.db.add(job)
        await self.db.flush()
        command_type = "browse_directory" if path else "browse_drives"
        payload = {"path": path} if path else {}
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=agent_id,
            command_type=command_type,
            payload=payload,
            idempotency_key=f"{command_type}:{job.id}",
            job_id=str(job.id),
        )
        return job

    async def start_validation(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        root: str,
        target_folders: list[str],
        target_files: list[str],
    ) -> BackgroundJob:
        agent = await self._active_agent(tenant_id, agent_id)
        config_hash = configuration_hash(
            agent_id, root, target_folders, target_files
        )
        job = BackgroundJob(
            tenant_id=agent.tenant_id,
            kind="agent_validate_structure",
            status="queued",
            phase="queued",
            resource_id=agent.id,
        )
        self.db.add(job)
        await self.db.flush()
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=agent_id,
            command_type="validate_structure",
            payload={
                "root": root,
                "targetFolders": target_folders,
                "targetFiles": target_files,
                "configurationHash": config_hash,
            },
            idempotency_key=f"validate:{job.id}",
            job_id=str(job.id),
        )
        return job

    async def start_cleanup_simulation(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        server_id: str,
        container_folder: str,
        max_properties: int,
        max_files: int = 50000,
        max_bytes: int = 20 * 1024**3,
    ) -> BackgroundJob:
        agent = await self._active_agent(tenant_id, agent_id)
        server = await self._configured_server(tenant_id, agent, server_id)
        job = BackgroundJob(
            tenant_id=agent.tenant_id,
            kind="agent_cleanup_simulation",
            status="queued",
            phase="queued",
            resource_id=agent.id,
        )
        self.db.add(job)
        await self.db.flush()
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=agent_id,
            command_type="simulate_structural_cleanup",
            payload={
                "root": server.base_path,
                "containerFolder": container_folder,
                "targetFolders": server.target_folders,
                "targetFiles": server.target_files,
                "maxProperties": max_properties,
                "maxFiles": max_files,
                "maxBytes": max_bytes,
            },
            idempotency_key=f"cleanup-simulate:{job.id}",
            job_id=str(job.id),
        )
        return job

    async def start_cleanup_direct(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        simulation_id: str,
        manifest_hash: str,
    ) -> BackgroundJob:
        agent = await self._active_agent(tenant_id, agent_id)
        job = BackgroundJob(
            tenant_id=agent.tenant_id,
            kind="agent_cleanup_direct",
            status="queued",
            phase="queued",
            resource_id=agent.id,
        )
        self.db.add(job)
        await self.db.flush()
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=agent_id,
            command_type="execute_structural_direct",
            payload={
                "simulationId": simulation_id,
                "manifestHash": manifest_hash,
            },
            idempotency_key=f"cleanup-direct:{job.id}",
            job_id=str(job.id),
            ttl_seconds=24 * 60 * 60,
        )
        return job

    async def start_cleanup_quarantine(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        simulation_id: str,
        manifest_hash: str,
    ) -> BackgroundJob:
        agent = await self._active_agent(tenant_id, agent_id)
        job = BackgroundJob(
            tenant_id=agent.tenant_id,
            kind="agent_cleanup_quarantine",
            status="queued",
            phase="queued",
            resource_id=agent.id,
        )
        self.db.add(job)
        await self.db.flush()
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=agent_id,
            command_type="execute_structural_quarantine",
            payload={
                "simulationId": simulation_id,
                "manifestHash": manifest_hash,
                "executionId": str(job.id),
            },
            idempotency_key=f"cleanup-quarantine:{job.id}",
            job_id=str(job.id),
        )
        return job

    async def start_quarantine_action(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        command_type: str,
        server_id: str,
        execution_id: str,
        relative_path: str | None = None,
    ) -> BackgroundJob:
        agent = await self._active_agent(tenant_id, agent_id)
        server = await self._configured_server(tenant_id, agent, server_id)
        job = BackgroundJob(
            tenant_id=agent.tenant_id,
            kind=f"agent_{command_type}",
            status="queued",
            phase="queued",
            resource_id=agent.id,
        )
        self.db.add(job)
        await self.db.flush()
        payload = {"root": server.base_path, "executionId": execution_id}
        if relative_path:
            payload["relativePath"] = relative_path
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=agent_id,
            command_type=command_type,
            payload=payload,
            idempotency_key=f"{command_type}:{job.id}",
            job_id=str(job.id),
        )
        return job

    async def get_job(self, tenant_id: str, job_id: str) -> dict[str, Any]:
        job = await self.admin_repo.get_job(tenant_id, job_id)
        if job is None:
            raise NotFoundError("Trabajo")
        return {
            "id": str(job.id),
            "kind": job.kind,
            "status": job.status,
            "phase": job.phase,
            "totalUnits": job.total_units,
            "processedUnits": job.processed_units,
            "foundCount": job.found_count,
            "result": job.result,
            "error": job.error,
            "cancelRequested": job.cancel_requested,
        }

    async def save_configuration(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        name: str,
        root: str,
        target_folders: list[str],
        target_files: list[str],
        validation_job_id: str,
        server_id: str | None,
    ) -> RemoteServer:
        agent = await self._active_agent(tenant_id, agent_id)
        job = await self.admin_repo.get_job(tenant_id, validation_job_id)
        if (
            job is None
            or job.kind != "agent_validate_structure"
            or job.status != "completed"
            or not (job.result or {}).get("valid")
        ):
            raise ConflictError(
                "Debe completar una validación satisfactoria antes de guardar",
                code="AGENT_VALIDATION_REQUIRED",
            )
        command = await self.admin_repo.get_command_for_job(job.id)
        expected_hash = configuration_hash(
            agent_id, root, target_folders, target_files
        )
        if (
            command is None
            or command.agent_id != agent.id
            or command.payload.get("configurationHash") != expected_hash
        ):
            raise ConflictError(
                "La configuración cambió; vuelva a validar",
                code="AGENT_VALIDATION_STALE",
            )
        server = None
        if server_id:
            server = await self.admin_repo.get_server(tenant_id, server_id)
            if server is None:
                raise NotFoundError("Servidor")
        if server is None:
            server = RemoteServer(
                tenant_id=tenant_uuid(tenant_id),
                name=name.strip(),
                transport="agent",
                agent_id=agent.id,
                base_path=root.strip(),
                allowlist=[],
                target_folders=target_folders,
                target_files=target_files,
                config_revision=1,
                configuration_hash=expected_hash,
                validated_at=datetime.now(timezone.utc),
            )
            self.db.add(server)
        else:
            server.name = name.strip()
            server.transport = "agent"
            server.agent_id = agent.id
            server.protocol = None
            server.host = None
            server.port = None
            server.username = None
            server.base_path = root.strip()
            server.allowlist = []
            server.target_folders = target_folders
            server.target_files = target_files
            server.config_revision += 1
            server.configuration_hash = expected_hash
            server.validated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return server

    async def cancel_job(self, tenant_id: str, job_id: str) -> dict[str, Any]:
        job = await self.admin_repo.get_job(tenant_id, job_id)
        if job is None:
            raise NotFoundError("Trabajo")
        if job.status in {"completed", "failed", "cancelled"}:
            return {"jobId": str(job.id), "cancelRequested": job.cancel_requested}
        job.cancel_requested = True
        job.phase = "cancellation_requested"
        command = await self.admin_repo.get_command_for_job(job.id)
        if command is not None and command.status == "pending":
            command.status = "cancelled"
            job.status = "cancelled"
            job.finished_at = datetime.now(timezone.utc)
        await self.db.flush()
        return {"jobId": str(job.id), "cancelRequested": True}

    async def _active_agent(self, tenant_id: str, agent_id: str) -> RemoteAgent:
        agent = await self.agent_repo.get_agent(tenant_id, agent_id)
        if agent is None:
            raise NotFoundError("Agente")
        if agent.status == "revoked" or agent.revoked_at is not None:
            raise ConflictError("El agente está revocado", code="AGENT_REVOKED")
        return agent

    async def _configured_server(
        self, tenant_id: str, agent: RemoteAgent, server_id: str
    ) -> RemoteServer:
        server = await self.admin_repo.get_server(tenant_id, server_id)
        if server is None:
            raise NotFoundError("Servidor")
        if (
            server.transport != "agent"
            or server.agent_id != agent.id
            or not server.base_path
            or not server.validated_at
        ):
            raise ConflictError(
                "El servidor no tiene una ruta validada para este agente",
                code="AGENT_SERVER_NOT_VALIDATED",
            )
        return server


def server_payload(server: RemoteServer) -> dict[str, Any]:
    return {
        "id": str(server.id),
        "name": server.name,
        "transport": server.transport,
        "agentId": str(server.agent_id) if server.agent_id else None,
        "root": server.base_path,
        "targetFolders": server.target_folders,
        "targetFiles": server.target_files,
        "configRevision": server.config_revision,
        "configurationHash": server.configuration_hash,
        "validatedAt": server.validated_at.isoformat() if server.validated_at else None,
    }

