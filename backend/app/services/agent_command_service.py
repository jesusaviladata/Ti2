from __future__ import annotations

import hashlib
import json
import uuid
import ntpath
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models.operations import AgentCommand, RemoteAgent
from app.repositories.agent_repository import AgentRepository


ALLOWED_COMMAND_TYPES = frozenset(
    {
        "browse_drives",
        "browse_directory",
        "validate_structure",
        "simulate_structural_cleanup",
        "execute_structural_quarantine",
        "restore_quarantine_item",
        "purge_quarantine_items",
        "cancel_job",
        "list_sql_databases",
        "run_backup_batch",
    }
)


def canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class AgentCommandService:
    def __init__(
        self,
        db: Any,
        *,
        repo: AgentRepository | Any | None = None,
        command_ttl_seconds: int = 120,
        now: Callable[[], datetime] | None = None,
    ):
        self.db = db
        self.repo = repo or AgentRepository(db)
        self.command_ttl_seconds = command_ttl_seconds
        self.now = now or (lambda: datetime.now(timezone.utc))

    async def create_command(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        command_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
        job_id: str | None = None,
    ) -> AgentCommand:
        if command_type not in ALLOWED_COMMAND_TYPES:
            raise DomainError(
                "AGENT_COMMAND_TYPE_INVALID",
                "El tipo de orden no está permitido",
                422,
            )
        normalized_key = idempotency_key.strip()
        if not normalized_key or len(normalized_key) > 128:
            raise DomainError(
                "AGENT_IDEMPOTENCY_KEY_INVALID",
                "La clave de idempotencia no es válida",
                422,
            )
        agent = await self.repo.get_agent(tenant_id, agent_id)
        if agent is None:
            raise NotFoundError("Agente")
        if agent.status == "revoked" or agent.revoked_at is not None:
            raise ConflictError(
                "El agente está revocado", code="AGENT_REVOKED"
            )
        existing = await self.repo.find_command_by_idempotency(
            agent.id, normalized_key
        )
        if existing is not None:
            return existing
        payload_bytes = canonical_json(payload)
        command = AgentCommand(
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            job_id=uuid.UUID(job_id) if job_id else None,
            command_type=command_type,
            payload=payload,
            payload_hash=hashlib.sha256(payload_bytes).hexdigest(),
            status="pending",
            idempotency_key=normalized_key,
            expires_at=self.now() + timedelta(seconds=self.command_ttl_seconds),
            result_summary={},
        )
        self.db.add(command)
        await self.db.flush()
        return command

    async def claim_next(self, agent: RemoteAgent) -> AgentCommand | None:
        command = await self.repo.claim_next_command(agent.id, self.now())
        if command is not None and command.job_id:
            job = await self.repo.get_background_job(command.job_id)
            if job is not None:
                job.status = "running"
                job.phase = "claimed"
        return command

    async def progress(
        self,
        agent: RemoteAgent,
        command_id: str,
        *,
        phase: str,
        processed_units: int,
        total_units: int,
        found_count: int,
    ) -> AgentCommand:
        command = await self._get(agent, command_id)
        if command.status in {"completed", "failed"}:
            return command
        self._require_claimed(command)
        if command.job_id:
            job = await self.repo.get_background_job(command.job_id)
            if job is not None:
                job.status = "running"
                job.phase = phase[:100]
                job.processed_units = max(0, processed_units)
                job.total_units = max(0, total_units)
                job.found_count = max(0, found_count)
        if command.command_type == "run_backup_batch":
            await self._mark_backups_running(command)
        await self.db.flush()
        return command

    async def complete(
        self,
        agent: RemoteAgent,
        command_id: str,
        result: dict[str, Any],
    ) -> AgentCommand:
        command = await self._get(agent, command_id)
        if command.status == "completed":
            return command
        if command.status == "failed":
            raise ConflictError(
                "La orden ya terminó con error", code="AGENT_COMMAND_FINALIZED"
            )
        self._require_claimed(command)
        now = self.now()
        command.status = "completed"
        command.completed_at = now
        command.result_summary = result
        if command.job_id:
            job = await self.repo.get_background_job(command.job_id)
            if job is not None:
                job.status = "completed"
                job.phase = "completed"
                job.result = result
                job.finished_at = now
        if command.command_type == "run_backup_batch":
            await self._complete_backups(command, result, now)
        await self.db.flush()
        return command

    async def fail(
        self,
        agent: RemoteAgent,
        command_id: str,
        error_code: str,
        error_message: str,
    ) -> AgentCommand:
        command = await self._get(agent, command_id)
        if command.status == "failed":
            return command
        if command.status == "completed":
            raise ConflictError(
                "La orden ya terminó correctamente", code="AGENT_COMMAND_FINALIZED"
            )
        self._require_claimed(command)
        now = self.now()
        command.status = "failed"
        command.completed_at = now
        command.error_code = error_code[:100]
        command.error_message = error_message[:1000]
        if command.job_id:
            job = await self.repo.get_background_job(command.job_id)
            if job is not None:
                job.status = "failed"
                job.phase = "failed"
                job.error = command.error_message
                job.finished_at = now
        if command.command_type == "run_backup_batch":
            await self._fail_backups(command, error_message, now)
        await self.db.flush()
        return command

    async def _backup_records(self, command: AgentCommand):
        from sqlalchemy import select
        from app.models.backup import Backup

        parsed: list[uuid.UUID] = []
        for value in command.payload.get("backupRecordIds", []):
            try:
                parsed.append(uuid.UUID(str(value)))
            except ValueError:
                continue
        if not parsed:
            return []
        result = await self.db.execute(
            select(Backup).where(
                Backup.id.in_(parsed), Backup.tenant_id == command.tenant_id
            )
        )
        return list(result.scalars().all())

    async def _mark_backups_running(self, command: AgentCommand) -> None:
        from app.models.backup import BackupStatus

        for record in await self._backup_records(command):
            if record.status == BackupStatus.pending:
                record.status = BackupStatus.running

    async def _complete_backups(
        self, command: AgentCommand, result: dict[str, Any], now: datetime
    ) -> None:
        from app.models.backup import BackupStatus

        by_database = {
            str(item.get("databaseName")): item
            for item in result.get("databases", [])
        }
        folder = str(result.get("folder") or "")
        for record in await self._backup_records(command):
            item = by_database.get(record.database_name)
            if item is None:
                record.status = BackupStatus.failed
                record.error_message = "El agente no reporto el archivo de esta base de datos"
            else:
                record.status = BackupStatus.completed
                record.file_path = ntpath.join(folder, str(item.get("fileName") or ""))
                record.file_size_bytes = int(item.get("fileSizeBytes") or 0)
                record.error_message = None
            record.finished_at = now

    async def _fail_backups(
        self, command: AgentCommand, error_message: str, now: datetime
    ) -> None:
        from app.models.backup import BackupStatus

        for record in await self._backup_records(command):
            record.status = BackupStatus.failed
            record.error_message = error_message[:2048]
            record.finished_at = now

    async def _get(self, agent: RemoteAgent, command_id: str) -> AgentCommand:
        try:
            parsed_id = uuid.UUID(command_id)
        except ValueError:
            raise NotFoundError("Orden") from None
        command = await self.repo.get_command_for_agent(agent.id, parsed_id)
        if command is None:
            raise NotFoundError("Orden")
        return command

    @staticmethod
    def _require_claimed(command: AgentCommand) -> None:
        if command.status != "claimed":
            raise ConflictError(
                "La orden no está en ejecución",
                code="AGENT_COMMAND_STATE_INVALID",
            )

