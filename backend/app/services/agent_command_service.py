from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models.backup import Backup, BackupStatus
from app.models.operations import AgentCommand, AgentConnectionProfile, RemoteAgent, RemoteCleanupExecution
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
        "retry_backup_delivery",
        "execute_structural_direct",
        "apply_connection_profiles",
        "test_connection_profile",
        "discover_agent_environment",
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
        ttl_seconds: int | None = None,
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
            expires_at=self.now()
            + timedelta(seconds=ttl_seconds or self.command_ttl_seconds),
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
        database: str | None = None,
        details: dict[str, Any] | None = None,
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
                if database or details:
                    current = dict(job.result or {})
                    current["progress"] = {
                        "database": database,
                        "details": details or {},
                    }
                    job.result = current
        await self._project_backup_progress(
            command,
            phase=phase,
            database=database,
            details=details or {},
            processed_units=processed_units,
            total_units=total_units,
        )
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
        if command.command_type == "run_backup_batch" and command.payload.get("origin"):
            if result.get("origin") != command.payload["origin"]:
                raise ConflictError(
                    "El origen reportado no coincide con la orden",
                    code="BACKUP_ORIGIN_MISMATCH",
                )
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
        await self._project_backup_complete(command, result, now)
        await self._project_cleanup_complete(command, result, now)
        await self._project_profile_complete(command, result, now)
        if command.command_type == "run_backup_batch":
            self._create_backup_success_notification(command, result)
        elif command.command_type == "execute_structural_direct":
            self._create_cleanup_notification(command, result, success=True)
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
        await self._project_backup_failure(command, command.error_message, now)
        await self._project_cleanup_failure(command, command.error_message, now)
        await self._project_profile_failure(command, command.error_message, now)
        if command.command_type == "execute_structural_direct":
            self._create_cleanup_notification(
                command,
                {"errorMessage": command.error_message},
                success=False,
            )
        await self.db.flush()
        return command

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

    async def _backups_for_command(self, command: AgentCommand) -> list[Backup]:
        if command.command_type not in {"run_backup_batch", "retry_backup_delivery"}:
            return []
        run_id = str(command.payload.get("runId") or "")
        if not run_id:
            return []
        result = await self.db.execute(
            select(Backup).where(
                Backup.tenant_id == command.tenant_id,
                Backup.run_id == run_id,
            )
        )
        return list(result.scalars().all())

    async def _project_backup_progress(
        self,
        command: AgentCommand,
        *,
        phase: str,
        database: str | None,
        details: dict[str, Any],
        processed_units: int,
        total_units: int,
    ) -> None:
        backups = await self._backups_for_command(command)
        if not backups:
            return
        by_name = {item.database_name: item for item in backups}
        item = by_name.get(database or "")
        if item is not None and phase in {"creating_bak", "validating_bak", "backup_ready"}:
            item.status = BackupStatus.running
            item.phase = phase
            item.started_at = item.started_at or self.now()
            item.progress_percent = {
                "creating_bak": 45,
                "validating_bak": 90,
                "backup_ready": 100,
            }[phase]
            if phase == "backup_ready":
                item.status = BackupStatus.completed
                item.validation_method = str(details.get("verificationMethod") or "restore_verifyonly")
                item.file_path = str(details.get("fileName") or "") or None
                item.file_size_bytes = int(details.get("fileSizeBytes") or 0) or None
                item.sha256_hash = str(details.get("fileSha256") or "") or None
                item.finished_at = self.now()
                item.delivery_status = "processing"
        elif phase in {"compressing", "archive_ready", "transferring"}:
            percent = {"compressing": 35, "archive_ready": 60, "transferring": 80}[phase]
            for backup in backups:
                if backup.status == BackupStatus.completed:
                    backup.delivery_status = "processing"
                    backup.delivery_phase = phase
                    backup.delivery_progress = percent
                    if phase == "archive_ready":
                        backup.archive_path = str(details.get("zipPath") or "") or None
                        backup.archive_size_bytes = int(details.get("zipSizeBytes") or 0) or None
                        backup.archive_sha256 = str(details.get("zipSha256") or "") or None

    async def _project_backup_complete(
        self, command: AgentCommand, result: dict[str, Any], now: datetime
    ) -> None:
        backups = await self._backups_for_command(command)
        if not backups:
            return
        results = {
            str(item.get("databaseName")): item
            for item in result.get("databases", [])
            if isinstance(item, dict)
        }
        transfer = result.get("transfer") if isinstance(result.get("transfer"), dict) else {}
        for backup in backups:
            data = results.get(backup.database_name)
            if data:
                backup.status = BackupStatus.completed
                backup.phase = "backup_ready"
                backup.progress_percent = 100
                backup.validation_method = str(data.get("verificationMethod") or "restore_verifyonly")
                backup.file_path = str(data.get("fileName") or "") or backup.file_path
                backup.file_size_bytes = int(data.get("fileSizeBytes") or 0) or backup.file_size_bytes
                backup.sha256_hash = str(data.get("fileSha256") or "") or backup.sha256_hash
                backup.finished_at = backup.finished_at or now
                local_only = transfer.get("type") == "local"
                backup.delivery_status = "local_ready" if local_only else "delivered"
                backup.delivery_phase = "local_ready" if local_only else "delivered"
                backup.delivery_progress = 100
                backup.archive_path = str(transfer.get("path") or result.get("zipPath") or "") or None
                backup.archive_size_bytes = int(result.get("zipSizeBytes") or 0) or None
                backup.archive_sha256 = str(result.get("zipSha256") or "") or None
            elif command.command_type == "retry_backup_delivery":
                backup.delivery_status = "delivered"
                backup.delivery_phase = "delivered"
                backup.delivery_progress = 100
                backup.delivery_error_message = None
                backup.archive_path = str(transfer.get("path") or result.get("zipPath") or backup.archive_path or "") or None
                backup.archive_size_bytes = int(result.get("zipSizeBytes") or 0) or backup.archive_size_bytes
                backup.archive_sha256 = str(result.get("zipSha256") or backup.archive_sha256 or "") or None

    async def _project_backup_failure(
        self, command: AgentCommand, message: str, now: datetime
    ) -> None:
        backups = await self._backups_for_command(command)
        if not backups:
            return
        for backup in backups:
            if backup.status == BackupStatus.completed:
                backup.delivery_status = "failed"
                backup.delivery_phase = "failed"
                backup.delivery_error_message = message
                continue
            if backup.status != BackupStatus.completed:
                backup.status = BackupStatus.failed
                backup.phase = "failed"
                backup.error_message = message
                backup.finished_at = now

    async def _project_cleanup_complete(
        self, command: AgentCommand, result: dict[str, Any], now: datetime
    ) -> None:
        if command.command_type != "execute_structural_direct" or not command.job_id:
            return
        job = await self.repo.get_background_job(command.job_id)
        if job is None or job.resource_id is None:
            return
        execution = (
            await self.db.execute(
                select(RemoteCleanupExecution).where(RemoteCleanupExecution.id == job.resource_id)
            )
        ).scalar_one_or_none()
        if execution is None:
            return
        failed = int(result.get("failedCount") or 0)
        execution.status = "completed_with_warnings" if failed else "completed"
        execution.summary = {**dict(execution.summary or {}), **result}
        execution.finished_at = now

    async def _project_cleanup_failure(
        self, command: AgentCommand, message: str, now: datetime
    ) -> None:
        if command.command_type != "execute_structural_direct" or not command.job_id:
            return
        job = await self.repo.get_background_job(command.job_id)
        if job is None or job.resource_id is None:
            return
        execution = (
            await self.db.execute(
                select(RemoteCleanupExecution).where(RemoteCleanupExecution.id == job.resource_id)
            )
        ).scalar_one_or_none()
        if execution is None:
            return
        execution.status = "failed"
        execution.summary = {**dict(execution.summary or {}), "error": message}
        execution.finished_at = now

    async def _project_profile_complete(
        self, command: AgentCommand, result: dict[str, Any], now: datetime
    ) -> None:
        if command.command_type == "apply_connection_profiles":
            revision = int(result.get("configRevision") or command.payload.get("configRevision") or 0)
            profile_ids = [
                uuid.UUID(str(item["id"]))
                for item in command.payload.get("profiles", [])
                if item.get("id")
            ]
            if profile_ids:
                rows = await self.db.execute(
                    select(AgentConnectionProfile).where(
                        AgentConnectionProfile.tenant_id == command.tenant_id,
                        AgentConnectionProfile.agent_id == command.agent_id,
                        AgentConnectionProfile.id.in_(profile_ids),
                    )
                )
                for item in rows.scalars().all():
                    item.applied_revision = item.desired_revision
                    item.sync_status = "applied"
                    item.last_error = None
            agent = await self.repo.get_agent(str(command.tenant_id), str(command.agent_id))
            if agent is not None:
                agent.applied_config_revision = max(agent.applied_config_revision or 0, revision)
        elif command.command_type == "test_connection_profile":
            profile_id = command.payload.get("profileId")
            if profile_id:
                rows = await self.db.execute(
                    select(AgentConnectionProfile).where(
                        AgentConnectionProfile.id == uuid.UUID(str(profile_id)),
                        AgentConnectionProfile.tenant_id == command.tenant_id,
                    )
                )
                item = rows.scalar_one_or_none()
                if item is not None:
                    item.last_test_status = "ok"
                    item.last_test_at = now
                    item.last_error = None

    async def _project_profile_failure(
        self, command: AgentCommand, message: str, now: datetime
    ) -> None:
        if command.command_type not in {"apply_connection_profiles", "test_connection_profile"}:
            return
        profile_ids = [
            str(item.get("id"))
            for item in command.payload.get("profiles", [])
            if item.get("id")
        ]
        if command.payload.get("profileId"):
            profile_ids.append(str(command.payload["profileId"]))
        if not profile_ids:
            return
        rows = await self.db.execute(
            select(AgentConnectionProfile).where(
                AgentConnectionProfile.tenant_id == command.tenant_id,
                AgentConnectionProfile.id.in_([uuid.UUID(value) for value in profile_ids]),
            )
        )
        for item in rows.scalars().all():
            if command.command_type == "apply_connection_profiles":
                item.sync_status = "error"
            else:
                item.last_test_status = "error"
                item.last_test_at = now
            item.last_error = message[:1000]

    def _create_backup_success_notification(
        self, command: AgentCommand, result: dict[str, Any]
    ) -> None:
        from app.models.operations import Notification

        databases = result.get("databases", [])
        total = len(databases)
        zip_name = str(result.get("zipFileName") or "archivo ZIP")
        self.db.add(
            Notification(
                tenant_id=command.tenant_id,
                user_id=None,
                kind="backup_success",
                title="Lote de respaldos completado",
                message=(
                    f"{total} base{'s' if total != 1 else ''} respaldada"
                    f"{'s' if total != 1 else ''} correctamente · {zip_name}"
                ),
                severity="success",
                metadata_json={
                    "jobId": str(command.job_id) if command.job_id else None,
                    "databaseCount": total,
                    "zipPath": result.get("zipPath"),
                },
            )
        )

    def _create_cleanup_notification(
        self, command: AgentCommand, result: dict[str, Any], *, success: bool
    ) -> None:
        from app.models.operations import Notification

        deleted = int(result.get("deletedCount") or 0)
        failed = int(result.get("failedCount") or 0)
        self.db.add(
            Notification(
                tenant_id=command.tenant_id,
                user_id=None,
                kind="cleanup_success" if success else "cleanup_failed",
                title="Limpieza de logs completada" if success else "Limpieza de logs fallida",
                message=(
                    f"{deleted} archivo(s) eliminado(s) · {failed} omitido(s)"
                    if success
                    else str(result.get("errorMessage") or "El agente no pudo completar la limpieza")
                ),
                severity="success" if success else "error",
                metadata_json={
                    "jobId": str(command.job_id) if command.job_id else None,
                    "deletedCount": deleted,
                    "failedCount": failed,
                    "bytesDeleted": int(result.get("bytesDeleted") or 0),
                },
            )
        )
