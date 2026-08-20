import uuid
from datetime import datetime, timezone

import pytest

from app.models.operations import AgentStorageAlert, RemoteAgent
from app.schemas.agent import AgentHealthPayload, AgentVolumePayload
from app.services.agent_health_service import AgentHealthService


class FakeHealthRepository:
    def __init__(self):
        self.volumes = {}
        self.alerts = {}

    async def upsert_volume(self, *, agent, volume, observed_at):
        self.volumes[volume.volume_key] = {
            "agent": agent,
            "volume": volume,
            "observed_at": observed_at,
        }

    async def get_open_alert(self, *, agent, volume_key):
        alert = self.alerts.get(volume_key)
        return alert if alert is not None and alert.status == "open" else None

    def add_alert(self, alert):
        self.alerts[alert.volume_key] = alert


def _agent() -> RemoteAgent:
    return RemoteAgent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        installation_id=str(uuid.uuid4()),
        hostname="CORE-01",
        os_version="Windows Server 2022",
        agent_version="0.4.0",
        public_key="x" * 44,
        status="connected",
    )


def _volume(*, free_bytes: int, total_bytes: int = 100_000_000_000):
    return AgentVolumePayload.model_validate(
        {
            "volumeKey": "D:",
            "label": "Data",
            "mountPoint": "D:\\",
            "totalBytes": total_bytes,
            "freeBytes": free_bytes,
            "usedPercent": (1 - free_bytes / total_bytes) * 100,
            "roles": ["backup", "destination"],
            "observedAt": "2026-08-20T20:00:00Z",
        }
    )


@pytest.mark.asyncio
async def test_record_heartbeat_updates_dedicated_liveness_and_opens_critical_alert():
    now = datetime(2026, 8, 20, 20, 1, tzinfo=timezone.utc)
    repo = FakeHealthRepository()
    agent = _agent()
    old_last_seen = datetime(2026, 8, 20, 19, 0, tzinfo=timezone.utc)
    agent.last_seen_at = old_last_seen
    health = AgentHealthPayload.model_validate(
        {"status": "busy", "currentOperation": "backup", "appliedConfigRevision": 7}
    )

    await AgentHealthService(repo=repo, now=lambda: now).record(
        agent=agent,
        health=health,
        volumes=[_volume(free_bytes=8_000_000_000)],
    )

    assert agent.last_heartbeat_at == now
    assert agent.last_seen_at == old_last_seen
    assert agent.health_status == "busy"
    assert agent.applied_config_revision == 7
    assert repo.volumes["D:"]["observed_at"].isoformat().startswith("2026-08-20")
    alert = repo.alerts["D:"]
    assert isinstance(alert, AgentStorageAlert)
    assert alert.severity == "critical"
    assert alert.status == "open"


@pytest.mark.asyncio
async def test_record_heartbeat_resolves_existing_alert_after_space_recovers():
    now = datetime(2026, 8, 20, 21, 0, tzinfo=timezone.utc)
    repo = FakeHealthRepository()
    agent = _agent()
    repo.alerts["D:"] = AgentStorageAlert(
        tenant_id=agent.tenant_id,
        agent_id=agent.id,
        volume_key="D:",
        severity="critical",
        status="open",
        opened_at=datetime(2026, 8, 20, 20, 0, tzinfo=timezone.utc),
        last_observed_at=datetime(2026, 8, 20, 20, 0, tzinfo=timezone.utc),
        thresholds={},
    )

    await AgentHealthService(repo=repo, now=lambda: now).record(
        agent=agent,
        health=None,
        volumes=[_volume(free_bytes=50_000_000_000)],
    )

    alert = repo.alerts["D:"]
    assert alert.status == "resolved"
    assert alert.resolved_at == now

