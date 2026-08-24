from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.errors import ConflictError
from app.models.operations import AgentConnectionProfile, AgentReplacementSession
from app.services.agent_replacement_service import AgentReplacementService


NOW = datetime(2026, 8, 21, 18, 0, tzinfo=timezone.utc)


class FakeDb:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid.uuid4()


class FakeEnrollment:
    async def issue_pairing_code(self, *args, **kwargs):
        return {"code": "ONE-TIME-CODE", "expiresAt": NOW.isoformat()}


class FakeRepo:
    def __init__(self, old, candidate=None, session=None):
        self.agents = {str(old.id): old}
        if candidate:
            self.agents[str(candidate.id)] = candidate
        self.session = session
        self.profiles = []
        self.plans = []
        self.tasks = []
        self.server = None
        self.active_work = False

    async def get_agent(self, _tenant_id, agent_id):
        return self.agents.get(str(agent_id))

    async def get_open_replacement_for_old(self, _tenant_id, _agent_id):
        return None

    async def get_replacement_session(self, _tenant_id, _session_id, *, for_update=False):
        return self.session

    async def list_agent_profiles(self, _tenant_id, agent_id):
        return [item for item in self.profiles if item.agent_id == agent_id]

    async def list_agent_backup_plans(self, _tenant_id, _agent_id):
        return self.plans

    async def list_file_backup_tasks(self, _tenant_id, _agent_id):
        return self.tasks

    async def get_remote_server_for_agent(self, _tenant_id, _agent_id):
        return self.server

    async def list_agent_volumes(self, _tenant_id, _agent_id):
        return []

    async def has_active_agent_work(self, _tenant_id, _agent_id):
        return self.active_work


def _agent(*, status="connected", hostname="CORE-OLD"):
    agent_id = uuid.uuid4()
    return SimpleNamespace(
        id=agent_id,
        tenant_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        hostname=hostname,
        agent_version="0.5.0",
        status=status,
        revoked_at=None,
        replaced_by_id=None,
        lineage_id=agent_id,
        desired_config_revision=3,
        applied_config_revision=3,
        health_status="connected",
        last_heartbeat_at=NOW,
        last_seen_at=NOW,
        metadata_json={"sqlInstances": [{"id": "sql", "label": "SQL"}]},
    )


@pytest.mark.asyncio
async def test_create_replacement_returns_one_time_code_without_touching_old_agent():
    old = _agent()
    db = FakeDb()
    repo = FakeRepo(old)
    service = AgentReplacementService(
        db,
        repo=repo,
        enrollment=FakeEnrollment(),
        now=lambda: NOW,
    )

    result = await service.create(
        str(old.tenant_id), str(old.id), str(uuid.uuid4())
    )

    assert result["code"] == "ONE-TIME-CODE"
    assert result["status"] == "awaiting_candidate"
    assert old.status == "connected"
    session = next(item for item in db.added if isinstance(item, AgentReplacementSession))
    assert session.expected_old_revision == 3


@pytest.mark.asyncio
async def test_confirm_transfers_public_configuration_and_revokes_old_only_at_cutover():
    old = _agent()
    candidate = _agent(status="replacement_pending", hostname="CORE-NEW")
    candidate.desired_config_revision = 0
    session = AgentReplacementSession(
        id=uuid.uuid4(),
        tenant_id=old.tenant_id,
        old_agent_id=old.id,
        candidate_agent_id=candidate.id,
        status="awaiting_confirmation",
        expected_old_revision=3,
        created_by=uuid.uuid4(),
        expires_at=NOW + timedelta(minutes=10),
        audit_json={},
    )
    repo = FakeRepo(old, candidate, session)
    sftp_profile = AgentConnectionProfile(
        id=uuid.uuid4(),
        tenant_id=old.tenant_id,
        agent_id=old.id,
        profile_type="destination",
        profile_key="central",
        label="Central",
        public_config={"type": "sftp", "path": "/backups"},
        secret_envelope="encrypted-for-old-agent",
        desired_revision=2,
        applied_revision=2,
        sync_status="applied",
        is_active=True,
    )
    repo.profiles = [sftp_profile]
    repo.plans = [
        SimpleNamespace(
            agent_id=old.id,
            sql_profile_id="sql-key",
            destination_profile_id=str(sftp_profile.id),
        )
    ]
    repo.tasks = [
        SimpleNamespace(
            agent_id=old.id,
            destination_profile_id=sftp_profile.id,
            config_revision=1,
            updated_at=NOW,
        )
    ]
    repo.server = SimpleNamespace(
        agent_id=old.id, config_revision=1
    )
    db = FakeDb()
    service = AgentReplacementService(
        db, repo=repo, now=lambda: NOW
    )

    result = await service.confirm(
        str(old.tenant_id), str(session.id), str(uuid.uuid4())
    )

    clone = next(item for item in db.added if isinstance(item, AgentConnectionProfile))
    assert clone.agent_id == candidate.id
    assert clone.public_config == sftp_profile.public_config
    assert clone.secret_envelope is None
    assert clone.sync_status == "requires_secret"
    assert repo.plans[0].agent_id == candidate.id
    assert repo.tasks[0].agent_id == candidate.id
    assert repo.tasks[0].destination_profile_id == clone.id
    assert repo.server.agent_id == candidate.id
    assert old.status == "revoked"
    assert candidate.status == "connected"
    assert session.status == "completed"
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_confirm_rejects_revision_change_or_active_work_without_cutover():
    old = _agent()
    candidate = _agent(status="replacement_pending", hostname="CORE-NEW")
    session = AgentReplacementSession(
        id=uuid.uuid4(),
        tenant_id=old.tenant_id,
        old_agent_id=old.id,
        candidate_agent_id=candidate.id,
        status="awaiting_confirmation",
        expected_old_revision=2,
        expires_at=NOW + timedelta(minutes=10),
        audit_json={},
    )
    repo = FakeRepo(old, candidate, session)
    repo.active_work = True
    service = AgentReplacementService(FakeDb(), repo=repo, now=lambda: NOW)

    with pytest.raises(ConflictError) as blocked:
        await service.confirm(
            str(old.tenant_id), str(session.id), str(uuid.uuid4())
        )

    assert blocked.value.code == "AGENT_REPLACEMENT_NOT_READY"
    assert old.status == "connected"
    assert candidate.status == "replacement_pending"


@pytest.mark.asyncio
async def test_cancel_is_idempotent_and_only_revokes_candidate():
    old = _agent()
    candidate = _agent(status="replacement_pending", hostname="CORE-NEW")
    session = AgentReplacementSession(
        id=uuid.uuid4(),
        tenant_id=old.tenant_id,
        old_agent_id=old.id,
        candidate_agent_id=candidate.id,
        status="awaiting_confirmation",
        expected_old_revision=3,
        expires_at=NOW + timedelta(minutes=10),
        audit_json={},
    )
    repo = FakeRepo(old, candidate, session)
    service = AgentReplacementService(FakeDb(), repo=repo, now=lambda: NOW)

    first = await service.cancel(
        str(old.tenant_id), str(session.id), str(uuid.uuid4())
    )
    second = await service.cancel(
        str(old.tenant_id), str(session.id), str(uuid.uuid4())
    )

    assert first["status"] == second["status"] == "cancelled"
    assert old.status == "connected"
    assert candidate.status == "revoked"
