from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.errors import DomainError
from app.services.agent_operation_service import AgentOperationService


class FakeDb:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid.uuid4()


class FakeAgents:
    def __init__(self, agent):
        self.agent = agent

    async def get_agent(self, tenant_id, agent_id):
        if str(self.agent.tenant_id) == tenant_id and str(self.agent.id) == agent_id:
            return self.agent
        return None


class FakeCommands:
    def __init__(self):
        self.calls = []

    async def create_command(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4(), **kwargs)


def _service(capabilities):
    tenant_id = uuid.uuid4()
    agent = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        status="connected",
        revoked_at=None,
        last_heartbeat_at=None,
        last_seen_at=datetime.now(timezone.utc),
        metadata_json={"capabilities": capabilities},
    )
    db = FakeDb()
    commands = FakeCommands()
    service = AgentOperationService(
        db,
        agents=FakeAgents(agent),
        commands=commands,
        admin=SimpleNamespace(),
    )
    return str(tenant_id), agent, db, commands, service


@pytest.mark.asyncio
async def test_managed_file_command_requires_capability():
    tenant_id, agent, _db, _commands, service = _service([])

    with pytest.raises(DomainError) as rejected:
        await service.start_managed_file_command(
            tenant_id,
            str(agent.id),
            command_type="simulate_file_backup",
            payload={"taskId": str(uuid.uuid4())},
            resource_id=uuid.uuid4(),
            idempotency_key="simulate:1",
        )

    assert rejected.value.code == "AGENT_FILE_BACKUP_UNSUPPORTED"


@pytest.mark.asyncio
async def test_managed_file_command_creates_durable_job_with_ttl_and_idempotency():
    tenant_id, agent, db, commands, service = _service(["file_backup_v1"])
    resource_id = uuid.uuid4()

    job = await service.start_managed_file_command(
        tenant_id,
        str(agent.id),
        command_type="run_file_backup",
        payload={"fileRunId": str(resource_id), "configRevision": 4},
        resource_id=resource_id,
        idempotency_key="file-run:1",
        ttl_seconds=3600,
    )

    assert job in db.added
    assert job.kind == "agent_run_file_backup"
    assert job.resource_id == resource_id
    assert commands.calls == [
        {
            "tenant_id": tenant_id,
            "agent_id": str(agent.id),
            "command_type": "run_file_backup",
            "payload": {"fileRunId": str(resource_id), "configRevision": 4},
            "idempotency_key": "file-run:1",
            "job_id": str(job.id),
            "ttl_seconds": 3600,
        }
    ]
