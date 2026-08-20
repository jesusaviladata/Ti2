from __future__ import annotations

from typing import Any

from app.repositories.agent_storage_repository import AgentStorageRepository
from app.services.agent_health_service import (
    CRITICAL_FREE_BYTES,
    CRITICAL_FREE_PERCENT,
    WARNING_FREE_BYTES,
    WARNING_FREE_PERCENT,
)


class AgentStorageService:
    def __init__(self, db: Any = None, *, repo: Any = None):
        self.repo = repo or AgentStorageRepository(db)

    @staticmethod
    def _threshold_payload(value=None) -> dict:
        return {
            "warningFreePercent": float(
                value.warning_free_percent if value else WARNING_FREE_PERCENT
            ),
            "warningFreeBytes": int(
                value.warning_free_bytes if value else WARNING_FREE_BYTES
            ),
            "criticalFreePercent": float(
                value.critical_free_percent if value else CRITICAL_FREE_PERCENT
            ),
            "criticalFreeBytes": int(
                value.critical_free_bytes if value else CRITICAL_FREE_BYTES
            ),
        }

    @staticmethod
    def _state(volume, thresholds: dict) -> tuple[str, float | None]:
        if volume.error or volume.total_bytes is None or volume.free_bytes is None:
            return "unknown", None
        if volume.total_bytes <= 0:
            return "unknown", None
        free_percent = volume.free_bytes / volume.total_bytes * 100
        if (
            free_percent <= thresholds["criticalFreePercent"]
            or volume.free_bytes <= thresholds["criticalFreeBytes"]
        ):
            return "critical", free_percent
        if (
            free_percent <= thresholds["warningFreePercent"]
            or volume.free_bytes <= thresholds["warningFreeBytes"]
        ):
            return "warning", free_percent
        return "healthy", free_percent

    async def inventory(self, tenant_id: str) -> dict:
        configured = await self.repo.get_thresholds(tenant_id)
        thresholds = self._threshold_payload(configured)
        rows = await self.repo.list_volumes(tenant_id)
        items = []
        for volume, agent in rows:
            state, free_percent = self._state(volume, thresholds)
            items.append(
                {
                    "agentId": str(agent.id),
                    "agentName": agent.hostname,
                    "volumeKey": volume.volume_key,
                    "label": volume.label,
                    "mountPoint": volume.mount_point,
                    "totalBytes": volume.total_bytes,
                    "freeBytes": volume.free_bytes,
                    "freePercent": free_percent,
                    "usedPercent": volume.used_percent,
                    "roles": volume.roles or [],
                    "observedAt": volume.observed_at.isoformat(),
                    "error": volume.error,
                    "state": state,
                }
            )
        rank = {"critical": 0, "warning": 1, "unknown": 2, "healthy": 3}
        items.sort(key=lambda item: (rank[item["state"]], item["freePercent"] or 101))
        return {
            "items": items,
            "total": len(items),
            "summary": items[0] if items else None,
            "thresholds": thresholds,
        }

    async def alerts(self, tenant_id: str, status: str | None = None) -> dict:
        rows = await self.repo.list_alerts(tenant_id, status)
        items = [
            {
                "id": str(alert.id),
                "agentId": str(agent.id),
                "agentName": agent.hostname,
                "volumeKey": alert.volume_key,
                "severity": alert.severity,
                "status": alert.status,
                "freeBytes": alert.free_bytes,
                "totalBytes": alert.total_bytes,
                "freePercent": alert.free_percent,
                "thresholds": alert.thresholds,
                "openedAt": alert.opened_at.isoformat(),
                "lastObservedAt": alert.last_observed_at.isoformat(),
                "resolvedAt": alert.resolved_at.isoformat() if alert.resolved_at else None,
            }
            for alert, agent in rows
        ]
        return {"items": items, "total": len(items)}

    async def update_thresholds(self, tenant_id: str, values: dict) -> dict:
        configured = await self.repo.upsert_thresholds(tenant_id, values)
        return self._threshold_payload(configured)
