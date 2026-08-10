from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.core.errors import ConflictError
from app.models.operations import AgentCommand, RemoteAgent
from app.services.agent_admin_service import AgentAdminService, configuration_hash


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


class FakeAdminRepo:
    def __init__(self):
        self.jobs = {}
        self.commands = {}

    async def get_job(self, _tenant_id, job_id):
        return self.jobs.get(job_id)

    async def get_command_for_job(self, job_id):
        return self.commands.get(job_id)

    async def get_server(self, _tenant_id, _server_id):
        return None


class FakeCommandService:
    def __init__(self, admin_repo, db, agent):
        self.admin_repo = admin_repo
        self.db = db
        self.agent = agent
        self.calls = []

    async def create_command(self, **kwargs):
        self.calls.append(kwargs)
        command = AgentCommand(
            id=uuid.uuid4(),
            tenant_id=self.agent.tenant_id,
            agent_id=self.agent.id,
            job_id=uuid.UUID(kwargs["job_id"]),
            command_type=kwargs["command_type"],
            payload=kwargs["payload"],
            payload_hash="0" * 64,
            idempotency_key=kwargs["idempotency_key"],
            expires_at=datetime.now(timezone.utc),
        )
        self.admin_repo.commands[command.job_id] = command
        return command


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
    db = FakeDb()
    admin_repo = FakeAdminRepo()
    commands = FakeCommandService(admin_repo, db, agent)
    service = AgentAdminService(
        db,
        agent_repo=FakeAgentRepo(agent),
        admin_repo=admin_repo,
        command_service=commands,
    )
    return agent, db, admin_repo, commands, service


@pytest.mark.asyncio
async def test_validation_queues_only_a_typed_command_with_configuration_hash():
    agent, _, admin_repo, commands, service = _fixture()
    folders = ["Log", "LogSec", "LogsRadian", "Respuesta"]
    files = ["BD_log.txt"]

    job = await service.start_validation(
        str(agent.tenant_id),
        str(agent.id),
        root="D:\\Ipsofactu",
        target_folders=folders,
        target_files=files,
    )
    admin_repo.jobs[str(job.id)] = job

    call = commands.calls[0]
    assert call["command_type"] == "validate_structure"
    assert call["payload"]["configurationHash"] == configuration_hash(
        str(agent.id), "D:\\Ipsofactu", folders, files
    )


@pytest.mark.asyncio
async def test_configuration_cannot_be_saved_until_matching_validation_completed():
    agent, db, admin_repo, _, service = _fixture()
    folders = ["Logs"]
    files = ["BD_log.txt"]
    job = await service.start_validation(
        str(agent.tenant_id),
        str(agent.id),
        root="D:\\Ipsofactu",
        target_folders=folders,
        target_files=files,
    )
    admin_repo.jobs[str(job.id)] = job

    with pytest.raises(ConflictError) as required:
        await service.save_configuration(
            str(agent.tenant_id),
            str(agent.id),
            name="Core Producción",
            root="D:\\Ipsofactu",
            target_folders=folders,
            target_files=files,
            validation_job_id=str(job.id),
            server_id=None,
        )
    assert required.value.code == "AGENT_VALIDATION_REQUIRED"

    job.status = "completed"
    job.result = {"valid": True, "propertiesDetected": 1500}
    server = await service.save_configuration(
        str(agent.tenant_id),
        str(agent.id),
        name="Core Producción",
        root="D:\\Ipsofactu",
        target_folders=folders,
        target_files=files,
        validation_job_id=str(job.id),
        server_id=None,
    )

    assert server.transport == "agent"
    assert server.protocol is None
    assert server.base_path == "D:\\Ipsofactu"
    assert server.config_revision == 1
    assert server in db.added


def test_configuration_hash_changes_when_any_target_changes():
    agent_id = str(uuid.uuid4())
    first = configuration_hash(agent_id, "D:\\Ipsofactu", ["Logs"], ["BD_log.txt"])
    second = configuration_hash(agent_id, "D:\\Ipsofactu", ["LogSec"], ["BD_log.txt"])
    assert first != second

