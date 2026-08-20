import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.agent_storage_service import AgentStorageService


class FakeStorageRepository:
    def __init__(self, rows):
        self.rows = rows
        self.seen_tenant = None

    async def get_thresholds(self, tenant_id):
        self.seen_tenant = tenant_id
        return None

    async def list_volumes(self, tenant_id):
        assert tenant_id == self.seen_tenant
        return self.rows


def _row(key, free, total, *, error=None):
    volume = SimpleNamespace(
        volume_key=key,
        label="Data",
        mount_point=f"{key}\\",
        total_bytes=total,
        free_bytes=free,
        used_percent=None if total is None or free is None else (1 - free / total) * 100,
        roles=["backup"],
        observed_at=datetime.now(timezone.utc),
        error=error,
    )
    agent = SimpleNamespace(id=uuid.uuid4(), hostname=f"CORE-{key[0]}")
    return volume, agent


@pytest.mark.asyncio
async def test_inventory_is_tenant_scoped_and_orders_most_critical_first():
    tenant_id = str(uuid.uuid4())
    repo = FakeStorageRepository(
        [
            _row("E:", 60 * 1024**3, 100 * 1024**3),
            _row("D:", 5 * 1024**3, 100 * 1024**3),
        ]
    )

    payload = await AgentStorageService(repo=repo).inventory(tenant_id)

    assert repo.seen_tenant == tenant_id
    assert payload["summary"]["volumeKey"] == "D:"
    assert payload["items"][0]["state"] == "critical"


@pytest.mark.asyncio
async def test_unreadable_volume_is_unknown_instead_of_zero_capacity():
    repo = FakeStorageRepository(
        [_row("Z:", None, None, error="No se pudo leer el volumen")]
    )

    payload = await AgentStorageService(repo=repo).inventory(str(uuid.uuid4()))

    assert payload["items"][0]["state"] == "unknown"
    assert payload["items"][0]["freeBytes"] is None
