from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock

from app.core.errors import ConflictError
from app.models.operations import AgentCommand, BackgroundJob, RemoteAgent
from app.models.operations import Notification
from app.services.agent_command_service import AgentCommandService


class FakeCommandDb:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        now = datetime.now(timezone.utc)
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid.uuid4()
            if getattr(value, "created_at", None) is None:
                value.created_at = now


class FakeCommandRepo:
    def __init__(self, agent: RemoteAgent):
        self.agent = agent
        self.commands: list[AgentCommand] = []
        self.jobs: dict[uuid.UUID, BackgroundJob] = {}

    async def get_agent(self, tenant_id: str, agent_id: str):
        if str(self.agent.tenant_id) == tenant_id and str(self.agent.id) == agent_id:
            return self.agent
        return None

    async def find_command_by_idempotency(self, agent_id, idempotency_key):
        return next(
            (item for item in self.commands if item.agent_id == agent_id and item.idempotency_key == idempotency_key),
            None,
        )

    async def claim_next_command(self, agent_id, now):
        item = next(
            (
                command
                for command in self.commands
                if command.agent_id == agent_id
                and command.status == "pending"
                and command.expires_at > now
            ),
            None,
        )
        if item:
            item.status = "claimed"
            item.claimed_at = now
        return item

    async def get_command_for_agent(self, agent_id, command_id):
        return next(
            (item for item in self.commands if item.agent_id == agent_id and item.id == command_id),
            None,
        )

    async def get_background_job(self, job_id):
        return self.jobs.get(job_id)


def _fixture():
    agent = RemoteAgent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        installation_id=str(uuid.uuid4()),
        hostname="CORE-01",
        agent_version="0.1.0",
        public_key="x" * 43,
        status="connected",
    )
    db = FakeCommandDb()
    repo = FakeCommandRepo(agent)
    return agent, db, repo, AgentCommandService(db, repo=repo)


@pytest.mark.asyncio
async def test_create_command_is_idempotent_and_claim_is_single_delivery():
    agent, db, repo, service = _fixture()

    first = await service.create_command(
        tenant_id=str(agent.tenant_id),
        agent_id=str(agent.id),
        command_type="browse_drives",
        payload={},
        idempotency_key="browse-drives-1",
    )
    repo.commands.append(first)
    duplicate = await service.create_command(
        tenant_id=str(agent.tenant_id),
        agent_id=str(agent.id),
        command_type="browse_drives",
        payload={},
        idempotency_key="browse-drives-1",
    )

    assert duplicate is first
    assert len(db.added) == 1
    assert await service.claim_next(agent) is first
    assert await service.claim_next(agent) is None


@pytest.mark.asyncio
async def test_duplicate_completion_is_idempotent_but_conflicting_transition_is_rejected():
    agent, db, repo, service = _fixture()
    command = AgentCommand(
        id=uuid.uuid4(),
        tenant_id=agent.tenant_id,
        agent_id=agent.id,
        command_type="browse_drives",
        payload={},
        payload_hash="0" * 64,
        status="claimed",
        idempotency_key="browse-1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    repo.commands.append(command)

    completed = await service.complete(agent, str(command.id), {"drives": ["C:\\\\", "D:\\\\"]})
    repeated = await service.complete(agent, str(command.id), {"ignored": True})

    assert repeated is completed
    assert repeated.result_summary == {"drives": ["C:\\\\", "D:\\\\"]}
    with pytest.raises(ConflictError):
        await service.fail(agent, str(command.id), "NETWORK_ERROR", "late failure")


@pytest.mark.asyncio
async def test_destructive_claim_is_not_automatically_requeued_after_uncertain_disconnect():
    agent, _, repo, service = _fixture()
    command = AgentCommand(
        id=uuid.uuid4(),
        tenant_id=agent.tenant_id,
        agent_id=agent.id,
        command_type="execute_structural_quarantine",
        payload={"simulationId": str(uuid.uuid4())},
        payload_hash="1" * 64,
        status="claimed",
        idempotency_key="execute-1",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        claimed_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    repo.commands.append(command)

    assert await service.claim_next(agent) is None
    assert command.status == "claimed"


@pytest.mark.asyncio
async def test_completed_backup_batch_creates_one_success_notification():
    agent, db, repo, service = _fixture()
    command = AgentCommand(
        id=uuid.uuid4(),
        tenant_id=agent.tenant_id,
        agent_id=agent.id,
        command_type="run_backup_batch",
        payload={"backupRecordIds": []},
        payload_hash="2" * 64,
        status="claimed",
        idempotency_key="backup-1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    repo.commands.append(command)
    service._complete_backups = AsyncMock()

    await service.complete(
        agent,
        str(command.id),
        {
            "databases": [
                {"databaseName": "Core"},
                {"databaseName": "Emision"},
            ],
            "zipFileName": "Backup_2026-08-12.zip",
        },
    )

    notifications = [item for item in db.added if isinstance(item, Notification)]
    assert len(notifications) == 1
    assert notifications[0].kind == "backup_success"
    assert "2 bases" in notifications[0].message

