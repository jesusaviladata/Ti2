from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operations import AgentStorageAlert, RemoteAgent
from app.repositories.agent_health_repository import AgentHealthRepository
from app.schemas.agent import AgentHealthPayload, AgentVolumePayload


GIB = 1024**3
WARNING_FREE_PERCENT = 20.0
WARNING_FREE_BYTES = 20 * GIB
CRITICAL_FREE_PERCENT = 10.0
CRITICAL_FREE_BYTES = 10 * GIB


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentHealthService:
    def __init__(
        self,
        db: AsyncSession | None = None,
        *,
        repo: AgentHealthRepository | None = None,
        now: Callable[[], datetime] = _utcnow,
    ):
        if repo is None and db is None:
            raise ValueError("db o repo es obligatorio")
        self.repo = repo or AgentHealthRepository(db)
        self.now = now

    @staticmethod
    def _severity(volume: AgentVolumePayload) -> tuple[str | None, float | None]:
        if (
            volume.error
            or volume.total_bytes is None
            or volume.total_bytes <= 0
            or volume.free_bytes is None
        ):
            return None, None
        free_percent = volume.free_bytes / volume.total_bytes * 100
        if free_percent <= CRITICAL_FREE_PERCENT or volume.free_bytes <= CRITICAL_FREE_BYTES:
            return "critical", free_percent
        if free_percent <= WARNING_FREE_PERCENT or volume.free_bytes <= WARNING_FREE_BYTES:
            return "warning", free_percent
        return "healthy", free_percent

    async def record(
        self,
        *,
        agent: RemoteAgent,
        health: AgentHealthPayload | None,
        volumes: list[AgentVolumePayload],
    ) -> None:
        now = self.now()
        agent.last_heartbeat_at = now
        agent.health_status = health.status if health else "connected"
        if health is not None:
            agent.applied_config_revision = health.applied_config_revision

        for volume in volumes:
            observed_at = volume.observed_at.astimezone(timezone.utc)
            await self.repo.upsert_volume(
                agent=agent,
                volume=volume,
                observed_at=observed_at,
            )
            severity, free_percent = self._severity(volume)
            if severity is None:
                continue

            alert = await self.repo.get_open_alert(
                agent=agent,
                volume_key=volume.volume_key,
            )
            if severity == "healthy":
                if alert is not None:
                    alert.status = "resolved"
                    alert.resolved_at = now
                    alert.last_observed_at = now
                    alert.free_bytes = volume.free_bytes
                    alert.total_bytes = volume.total_bytes
                    alert.free_percent = free_percent
                continue

            thresholds = {
                "warningFreePercent": WARNING_FREE_PERCENT,
                "warningFreeBytes": WARNING_FREE_BYTES,
                "criticalFreePercent": CRITICAL_FREE_PERCENT,
                "criticalFreeBytes": CRITICAL_FREE_BYTES,
            }
            if alert is None:
                self.repo.add_alert(
                    AgentStorageAlert(
                        tenant_id=agent.tenant_id,
                        agent_id=agent.id,
                        volume_key=volume.volume_key,
                        severity=severity,
                        status="open",
                        free_bytes=volume.free_bytes,
                        total_bytes=volume.total_bytes,
                        free_percent=free_percent,
                        thresholds=thresholds,
                        opened_at=now,
                        last_observed_at=now,
                    )
                )
            else:
                alert.severity = severity
                alert.free_bytes = volume.free_bytes
                alert.total_bytes = volume.total_bytes
                alert.free_percent = free_percent
                alert.thresholds = thresholds
                alert.last_observed_at = now
