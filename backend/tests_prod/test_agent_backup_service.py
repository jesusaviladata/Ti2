from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.backup import Backup, BackupDestination, BackupStatus
from app.models.operations import RemoteAgent
from app.services.agent_backup_service import AgentBackupService


class FakeDb:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid.uuid4()
            if getattr(value, "created_at", None) is None:
                value.created_at = datetime.now(timezone.utc)


class FakeAgentRepo:
    def __init__(self, agent):
        self.agent = agent

    async def get_agent(self, tenant_id, agent_id):
        if tenant_id == str(self.agent.tenant_id) and agent_id == str(self.agent.id):
            return self.agent
        return None


class FakeCommands:
    def __init__(self):
        self.calls = []

    async def create_command(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_backup_creates_one_record_per_database_and_one_agent_command():
    agent = RemoteAgent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        installation_id=str(uuid.uuid4()),
        hostname="DX-SQL-01",
        agent_version="0.2.0",
        public_key="x" * 43,
        status="connected",
        metadata_json={
            "sqlInstances": [{"id": "local", "label": "SQL local"}],
            "backupDestinations": [{"id": "central", "label": "Central", "type": "sftp"}],
        },
    )
    db = FakeDb()
    commands = FakeCommands()
    service = AgentBackupService(
        db,
        agent_repo=FakeAgentRepo(agent),
        command_service=commands,
    )

    job, records = await service.start_backup(
        str(agent.tenant_id),
        str(agent.id),
        sql_profile_id="local",
        database_names=["ERP", "Facturacion", "ERP"],
        backup_type="full",
        destination_profile_id="central",
    )

    assert [item.database_name for item in records] == ["ERP", "Facturacion"]
    assert all(item.status == BackupStatus.pending for item in records)
    assert all(item.destination == BackupDestination.secondary_server for item in records)
    assert len([item for item in db.added if isinstance(item, Backup)]) == 2
    assert job.total_units == 2
    assert commands.calls[0]["command_type"] == "run_backup_batch"
    assert commands.calls[0]["payload"]["databaseNames"] == ["ERP", "Facturacion"]
