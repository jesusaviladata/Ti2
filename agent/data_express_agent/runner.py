from __future__ import annotations

import logging
import threading
from typing import Any
from pathlib import Path

from .backup import BackupError, BackupExecutor
from .client import AgentClient, AgentClientError
from .cleanup import CleanupError, StructuralCleanupExecutor
from .explorer import ExplorerError, WindowsExplorer
from .health import AgentHealthSupervisor
from .journal import ExecutionJournal
from .runner_utils import retry_delay
from .storage import StorageCollector
from .profiles import ManagedProfileStore, ProfileApplyError
from .discovery import discover_environment
from .protocol import MANAGED_FILE_COMMAND_TYPES


logger = logging.getLogger("data_express_agent")

DESTRUCTIVE_COMMANDS = frozenset(
    {
        "execute_structural_quarantine",
        "execute_structural_direct",
        "restore_quarantine_item",
        "purge_quarantine_items",
        "run_backup_batch",
        "retry_backup_delivery",
        "run_file_backup",
        "resume_file_backup",
        "run_file_restore",
    }
)


class AgentRunner:
    def __init__(
        self,
        client: AgentClient,
        journal: ExecutionJournal,
        *,
        explorer: WindowsExplorer | None = None,
        backup_executor: BackupExecutor | None = None,
        cleanup_executor: StructuralCleanupExecutor | None = None,
        health_supervisor: AgentHealthSupervisor | None = None,
        file_backup_executor: Any | None = None,
    ):
        self.client = client
        self.journal = journal
        self.explorer = explorer or WindowsExplorer()
        config = getattr(client, "config", None)
        identity = getattr(client, "identity", None)
        data_dir = getattr(config, "data_dir", None) or journal.path.parent
        self.profile_store = (
            ManagedProfileStore(Path(data_dir) / "managed-profiles.json", identity)
            if identity is not None
            else None
        )
        if self.profile_store is not None:
            self.profile_store.import_legacy_profiles(
                getattr(config, "sql_instances", ()),
                getattr(config, "backup_destinations", ()),
            )
            sql_profiles, destination_profiles = self.profile_store.runtime_profiles()
        else:
            sql_profiles = getattr(config, "sql_instances", ())
            destination_profiles = getattr(config, "backup_destinations", ())
        self.backups = backup_executor or BackupExecutor(
            sql_profiles=sql_profiles,
            destination_profiles=destination_profiles,
        )
        self.cleanup = cleanup_executor or StructuralCleanupExecutor(journal.path.parent)
        self.file_backups = file_backup_executor
        if health_supervisor is not None:
            self.health = health_supervisor
        else:
            storage = StorageCollector.from_profiles(
                getattr(config, "sql_instances", ()),
                getattr(config, "backup_destinations", ()),
                getattr(config, "cleanup_roots", ()),
            )
            self.health = AgentHealthSupervisor(
                client,
                interval_seconds=float(getattr(config, "heartbeat_interval_seconds", 30)),
                volume_collector=storage.collect,
                file_backup_enabled=file_backup_executor is not None,
                catalog_revision_factory=(
                    (lambda: int(getattr(file_backup_executor, "catalog_revision", 0)))
                    if file_backup_executor is not None
                    else None
                ),
                metadata_factory=self._public_metadata,
            )
        self.handlers = {
            "browse_drives": self._browse_drives,
            "browse_directory": self._browse_directory,
            "validate_structure": self._validate_structure,
            "list_sql_databases": self._list_sql_databases,
            "run_backup_batch": self._run_backup_batch,
            "retry_backup_delivery": self._retry_backup_delivery,
            "simulate_structural_cleanup": self._simulate_structural_cleanup,
            "execute_structural_quarantine": self._execute_structural_quarantine,
            "execute_structural_direct": self._execute_structural_direct,
            "restore_quarantine_item": self._restore_quarantine_item,
            "purge_quarantine_items": self._purge_quarantine_items,
            "apply_connection_profiles": self._apply_connection_profiles,
            "test_connection_profile": self._test_connection_profile,
            "discover_agent_environment": self._discover_agent_environment,
        }
        if self.file_backups is not None:
            for command_type in MANAGED_FILE_COMMAND_TYPES:
                self.handlers[command_type] = (
                    lambda payload, command_id, managed_type=command_type: self._managed_file_command(
                        managed_type, payload, command_id
                    )
                )

    def _public_metadata(self) -> dict[str, Any]:
        import platform

        profiles = (
            self.profile_store.public_profiles()
            if self.profile_store is not None
            else getattr(self.client.config, "public_metadata", lambda: {})()
        )
        metadata = {"hostname": platform.node(), "os": platform.platform(), **profiles}
        if self.file_backups is not None:
            from .protocol import FILE_BACKUP_CAPABILITY

            metadata["capabilities"] = [FILE_BACKUP_CAPABILITY]
            metadata["fileCatalogRevision"] = max(
                0, int(getattr(self.file_backups, "catalog_revision", 0))
            )
        return metadata

    def recover_interrupted(self) -> None:
        for command_id, entry in self.journal.interrupted():
            command = entry.get("command", {})
            command_type = command.get("type", "")
            if command_type in DESTRUCTIVE_COMMANDS:
                self.journal.record_failed(
                    command_id,
                    "MANUAL_REVIEW_REQUIRED",
                    "La conexión se interrumpió durante una operación destructiva; revise el estado y simule nuevamente.",
                )
                continue
            try:
                result = self._execute(command)
                self.journal.record_completed(command_id, result)
            except (ExplorerError, BackupError, CleanupError, ProfileApplyError, ValueError, KeyError) as exc:
                code = getattr(exc, "code", "COMMAND_FAILED")
                self.journal.record_failed(command_id, code, str(exc))

    def flush_reports(self) -> None:
        for command_id, entry in self.journal.unreported():
            if entry["status"] == "completed":
                self.client.complete(command_id, entry.get("result", {}))
            else:
                self.client.fail(
                    command_id,
                    entry.get("errorCode", "COMMAND_FAILED"),
                    entry.get("errorMessage", "La orden no pudo completarse"),
                )
            self.journal.mark_reported(command_id)

    def run_once(self) -> bool:
        self.flush_reports()
        command = self.client.next_command()
        if command is None:
            return False
        command_id = command["id"]
        previous = self.journal.get(command_id)
        if previous:
            if previous.get("status") == "started":
                self.recover_interrupted()
            self.flush_reports()
            return True
        self.journal.record_started(command)
        self.health.begin_operation(str(command.get("type") or "command"))
        try:
            result = self._execute(command)
            self.journal.record_completed(command_id, result)
        except (ExplorerError, BackupError, CleanupError, ProfileApplyError, ValueError, KeyError) as exc:
            code = getattr(exc, "code", "COMMAND_FAILED")
            logger.exception("Command %s failed: %s", command_id, code)
            self.journal.record_failed(command_id, code, str(exc))
        finally:
            self.health.end_operation()
        self.flush_reports()
        return True

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        stop = stop_event or threading.Event()
        self.recover_interrupted()
        attempt = 0
        self.health.start(stop)
        try:
            while not stop.is_set():
                try:
                    self.run_once()
                    attempt = 0
                except AgentClientError as exc:
                    if not exc.recoverable:
                        logger.error("Agent request stopped: %s", exc.code)
                        raise
                    delay = retry_delay(attempt)
                    attempt += 1
                    logger.warning("Railway unavailable; retrying in %.1fs", delay)
                    stop.wait(delay)
                except Exception:
                    logger.exception("Unexpected agent failure")
                    stop.wait(retry_delay(attempt))
                    attempt += 1
            if self.health.fatal_error is not None:
                raise self.health.fatal_error
        finally:
            self.health.stop()
            self.client.close()

    def _execute(self, command: dict[str, Any]) -> dict[str, Any]:
        command_type = command["type"]
        handler = self.handlers.get(command_type)
        if handler is None:
            raise ExplorerError(
                "COMMAND_TYPE_UNSUPPORTED", "El tipo de orden no está implementado"
            )
        return handler(command.get("payload", {}), command["id"])

    def _browse_drives(self, _payload: dict[str, Any], _command_id: str):
        return self.explorer.browse_drives()

    def _browse_directory(self, payload: dict[str, Any], _command_id: str):
        return self.explorer.browse_directory(str(payload["path"]))

    def _validate_structure(self, payload: dict[str, Any], command_id: str):
        def progress(processed: int, total: int) -> None:
            if processed == total or processed % 50 == 0:
                self.client.progress(
                    command_id,
                    {
                        "phase": "validating_structure",
                        "processedUnits": processed,
                        "totalUnits": total,
                        "foundCount": 0,
                    },
                )

        return self.explorer.validate_structure(
            str(payload["root"]),
            target_folders=list(payload.get("targetFolders", [])),
            target_files=list(payload.get("targetFiles", [])),
            progress=progress,
        )

    def _list_sql_databases(self, payload: dict[str, Any], _command_id: str):
        return self.backups.list_databases(str(payload["sqlProfileId"]))

    def _run_backup_batch(self, payload: dict[str, Any], command_id: str):
        return self.backups.run_batch(
            payload,
            progress=lambda value: self.client.progress(command_id, value),
        )

    def _managed_file_command(
        self, command_type: str, payload: dict[str, Any], command_id: str
    ) -> dict[str, Any]:
        if command_type not in MANAGED_FILE_COMMAND_TYPES or self.file_backups is None:
            raise ExplorerError(
                "COMMAND_TYPE_UNSUPPORTED", "El tipo de orden no está implementado"
            )
        return self.file_backups.execute(
            command_type,
            payload,
            progress=lambda value: self.client.progress(command_id, value),
        )

    def _retry_backup_delivery(self, payload: dict[str, Any], command_id: str):
        return self.backups.retry_delivery(
            payload,
            progress=lambda value: self.client.progress(command_id, value),
        )

    def _simulate_structural_cleanup(self, payload: dict[str, Any], command_id: str):
        return self.cleanup.simulate(
            payload,
            progress=lambda value: self.client.progress(command_id, value),
        )

    def _execute_structural_quarantine(self, payload: dict[str, Any], command_id: str):
        return self.cleanup.execute_quarantine(
            payload,
            progress=lambda value: self.client.progress(command_id, value),
        )

    def _execute_structural_direct(self, payload: dict[str, Any], command_id: str):
        return self.cleanup.execute_direct(
            payload,
            progress=lambda value: self.client.progress(command_id, value),
        )

    def _restore_quarantine_item(self, payload: dict[str, Any], _command_id: str):
        return self.cleanup.restore(payload)

    def _purge_quarantine_items(self, payload: dict[str, Any], _command_id: str):
        return self.cleanup.purge(payload)

    def _apply_connection_profiles(self, payload: dict[str, Any], _command_id: str):
        if self.profile_store is None:
            raise ProfileApplyError("PROFILE_STORE_UNAVAILABLE", "No se pudo abrir el almacén de perfiles")
        result = self.profile_store.apply(payload)
        sql_profiles, destination_profiles = self.profile_store.runtime_profiles()
        self.backups.sql_profiles = sql_profiles
        self.backups.destination_profiles = destination_profiles
        self.health.set_applied_config_revision(int(result["configRevision"]))
        return result

    def _test_connection_profile(self, payload: dict[str, Any], _command_id: str):
        if self.profile_store is None:
            raise ProfileApplyError("PROFILE_STORE_UNAVAILABLE", "No se pudo abrir el almacén de perfiles")
        return self.profile_store.test_profile(str(payload["profileId"]))

    def _discover_agent_environment(self, _payload: dict[str, Any], _command_id: str):
        return discover_environment(self.backups.sql_profiles, self.backups.destination_profiles)

