from __future__ import annotations

import logging
import platform
import threading
from typing import Any, Callable

from .client import AgentClient, AgentClientError
from .runner_utils import retry_delay
from .protocol import FILE_BACKUP_CAPABILITY


logger = logging.getLogger("data_express_agent")


class AgentHealthSupervisor:
    def __init__(
        self,
        client: AgentClient,
        *,
        interval_seconds: float = 30.0,
        metadata_factory: Callable[[], dict[str, Any]] | None = None,
        volume_collector: Callable[[], list[dict[str, Any]]] | None = None,
        file_backup_enabled: bool = False,
        catalog_revision_factory: Callable[[], int] | None = None,
    ):
        self.client = client
        self.interval_seconds = interval_seconds
        self.metadata_factory = metadata_factory or self._default_metadata
        self.volume_collector = volume_collector or (lambda: [])
        self.file_backup_enabled = file_backup_enabled
        self.catalog_revision_factory = catalog_revision_factory
        self._lock = threading.Lock()
        self._status = "connected"
        self._current_operation: str | None = None
        self._applied_config_revision = 0
        self._local_stop = threading.Event()
        self._external_stop: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self.fatal_error: AgentClientError | None = None

    def _default_metadata(self) -> dict[str, Any]:
        public_metadata = getattr(self.client.config, "public_metadata", lambda: {})
        metadata = {
            "hostname": platform.node(),
            "os": platform.platform(),
            **public_metadata(),
        }
        if self.file_backup_enabled:
            metadata["capabilities"] = [FILE_BACKUP_CAPABILITY]
            revision = (
                self.catalog_revision_factory()
                if self.catalog_revision_factory is not None
                else 0
            )
            metadata["fileCatalogRevision"] = max(0, int(revision))
        return metadata

    def start(self, stop_event: threading.Event) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._external_stop = stop_event
        self._local_stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="DataExpressAgent-Health",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._local_stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def begin_operation(self, operation: str) -> None:
        with self._lock:
            self._status = "busy"
            self._current_operation = operation[:80]

    def end_operation(self) -> None:
        with self._lock:
            self._status = "connected"
            self._current_operation = None

    def mark_degraded(self) -> None:
        with self._lock:
            self._status = "degraded"

    def set_applied_config_revision(self, revision: int) -> None:
        with self._lock:
            self._applied_config_revision = max(0, revision)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self._status,
                "currentOperation": self._current_operation,
                "appliedConfigRevision": self._applied_config_revision,
            }

    def _stopped(self) -> bool:
        return self._local_stop.is_set() or bool(
            self._external_stop and self._external_stop.is_set()
        )

    def _wait(self, seconds: float) -> None:
        remaining = max(0.0, seconds)
        while remaining > 0 and not self._stopped():
            step = min(remaining, 0.25)
            self._local_stop.wait(step)
            remaining -= step

    def _run(self) -> None:
        attempt = 0
        confirmed = False
        while not self._stopped():
            try:
                self.client.heartbeat(
                    self.metadata_factory(),
                    health=self.snapshot(),
                    volumes=self.volume_collector(),
                )
                if not confirmed:
                    logger.info(
                        "Heartbeat confirmado con backend para agente %s",
                        getattr(self.client.config, "agent_version", "desconocida"),
                    )
                    confirmed = True
                attempt = 0
                self._wait(self.interval_seconds)
            except AgentClientError as exc:
                if not exc.recoverable:
                    self.fatal_error = exc
                    if self._external_stop is not None:
                        self._external_stop.set()
                    logger.error("Heartbeat detenido: %s", exc.code)
                    return
                delay = retry_delay(attempt)
                attempt += 1
                logger.warning("Heartbeat no disponible; reintento en %.1fs", delay)
                self._wait(delay)
            except Exception:
                logger.exception("No se pudo recopilar o enviar la salud del agente")
                self.mark_degraded()
                self._wait(retry_delay(attempt))
                attempt += 1
