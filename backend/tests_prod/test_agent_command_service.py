from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock

from app.core.errors import ConflictError
from app.models.operations import AgentCommand, BackgroundJob, RemoteAgent
from app.models.file_backup import FileBackupRun, FileBackupRunStatus, FileBackupStrategy
from app.models.operations import Notification
from app.services.agent_command_service import ALLOWED_COMMAND_TYPES, AgentCommandService


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
        self.file_runs: dict[uuid.UUID, FileBackupRun] = {}

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

    async def get_file_backup_run(self, tenant_id, agent_id, run_id):
        item = self.file_runs.get(run_id)
        if item and item.tenant_id == tenant_id and item.agent_id == agent_id:
            return item
        return None

    async def get_file_restore_job(self, tenant_id, agent_id, restore_id):
        return None


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


def test_managed_file_commands_are_explicitly_allowlisted():
    assert {
        "apply_file_backup_config",
        "simulate_file_backup",
        "run_file_backup",
        "resume_file_backup",
        "cancel_file_backup",
        "simulate_file_restore",
        "run_file_restore",
        "test_file_destination",
    } <= ALLOWED_COMMAND_TYPES


@pytest.mark.asyncio
async def test_replacement_candidate_cannot_receive_or_claim_operational_commands():
    agent, _db, repo, service = _fixture()
    agent.status = "replacement_pending"

    with pytest.raises(ConflictError) as blocked:
        await service.create_command(
            tenant_id=str(agent.tenant_id),
            agent_id=str(agent.id),
            command_type="browse_drives",
            payload={},
            idempotency_key="candidate-command",
        )

    assert blocked.value.code == "AGENT_REPLACEMENT_PENDING"
    assert await service.claim_next(agent) is None
    assert repo.commands == []


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
async def test_create_command_can_extend_ttl_for_queued_scheduled_batches():
    agent, _db, _repo, service = _fixture()
    fixed_now = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
    service.now = lambda: fixed_now

    command = await service.create_command(
        tenant_id=str(agent.tenant_id),
        agent_id=str(agent.id),
        command_type="run_backup_batch",
        payload={},
        idempotency_key="scheduled-batch-1",
        ttl_seconds=24 * 60 * 60,
    )

    assert command.expires_at == fixed_now + timedelta(hours=24)


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
async def test_file_backup_progress_and_completion_project_aggregates_idempotently():
    agent, _db, repo, service = _fixture()
    run = FileBackupRun(
        id=uuid.uuid4(),
        tenant_id=agent.tenant_id,
        task_id=uuid.uuid4(),
        agent_id=agent.id,
        config_revision=2,
        strategy=FileBackupStrategy.full,
        status=FileBackupRunStatus.queued,
        phase="queued",
        progress_percent=0,
        files_processed=0,
        bytes_processed=0,
        summary={},
    )
    repo.file_runs[run.id] = run
    command = AgentCommand(
        id=uuid.uuid4(),
        tenant_id=agent.tenant_id,
        agent_id=agent.id,
        command_type="run_file_backup",
        payload={"fileRunId": str(run.id)},
        payload_hash="5" * 64,
        status="claimed",
        idempotency_key="file-run-1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    repo.commands.append(command)

    await service.progress(
        agent,
        str(command.id),
        phase="copying",
        processed_units=25,
        total_units=100,
        found_count=100,
        details={"bytesProcessed": 4096, "bytesTotal": 16384},
    )

    assert run.status == FileBackupRunStatus.running
    assert run.phase == "copying"
    assert run.progress_percent == 25
    assert run.files_processed == 25
    assert run.bytes_processed == 4096

    first = await service.complete(
        agent,
        str(command.id),
        {"status": "completed", "artifacts": 1},
    )
    repeated = await service.complete(
        agent,
        str(command.id),
        {"status": "failed", "artifacts": 99},
    )

    assert repeated is first
    assert run.status == FileBackupRunStatus.completed
    assert run.progress_percent == 100
    assert run.summary == {"status": "completed", "artifacts": 1}


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


@pytest.mark.asyncio
async def test_completed_direct_cleanup_creates_success_notification():
    agent, db, repo, service = _fixture()
    command = AgentCommand(
        id=uuid.uuid4(),
        tenant_id=agent.tenant_id,
        agent_id=agent.id,
        command_type="execute_structural_direct",
        payload={"simulationId": str(uuid.uuid4())},
        payload_hash="3" * 64,
        status="claimed",
        idempotency_key="cleanup-direct-1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    repo.commands.append(command)

    await service.complete(
        agent,
        str(command.id),
        {"deletedCount": 12, "failedCount": 1, "bytesDeleted": 4096},
    )

    notifications = [item for item in db.added if isinstance(item, Notification)]
    assert len(notifications) == 1
    assert notifications[0].kind == "cleanup_success"
    assert "12 archivo" in notifications[0].message


@pytest.mark.asyncio
async def test_backup_completion_rejects_origin_different_from_signed_command():
    agent, _db, repo, service = _fixture()
    expected = {
        "agent": {"id": str(agent.id), "hostname": "CORE-01"},
        "sqlProfile": {"id": "main", "label": "SQL"},
        "destinationProfile": None,
        "sourceLabel": "CORE-01 · SQL",
    }
    command = AgentCommand(
        id=uuid.uuid4(),
        tenant_id=agent.tenant_id,
        agent_id=agent.id,
        command_type="run_backup_batch",
        payload={"origin": expected},
        payload_hash="4" * 64,
        status="claimed",
        idempotency_key="backup-origin-1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    repo.commands.append(command)

    with pytest.raises(ConflictError) as mismatch:
        await service.complete(
            agent,
            str(command.id),
            {"origin": {**expected, "sourceLabel": "OTRO · SQL"}},
        )

    assert mismatch.value.code == "BACKUP_ORIGIN_MISMATCH"

