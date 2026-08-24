from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.agent_profile_service import (
    AgentProfileService,
    serialize_managed_profile,
)


class FakeDb:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None


class FakeAgents:
    def __init__(self, agent):
        self.agent = agent

    async def get_agent(self, _tenant_id, _agent_id):
        return self.agent


class FakeProfiles:
    def __init__(self):
        self.added = []

    def add(self, item):
        self.added.append(item)


class FakeCommands:
    def __init__(self):
        self.created = []

    async def create_command(self, **kwargs):
        self.created.append(kwargs)


@pytest.mark.asyncio
async def test_non_migrable_profile_is_saved_as_requires_secret_without_queueing():
    tenant_id = uuid.uuid4()
    agent = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        status="online",
        revoked_at=None,
        desired_config_revision=0,
        metadata_json={},
        encryption_public_key=None,
    )
    profiles = FakeProfiles()
    commands = FakeCommands()
    service = AgentProfileService(
        FakeDb(),
        agents=FakeAgents(agent),
        profiles=profiles,
        commands=commands,
    )

    item = await service.save(
        str(tenant_id),
        str(agent.id),
        profile_id=None,
        profile_type="destination",
        profile_key="legacy-sftp",
        label="Destino anterior",
        public_config={
            "type": "sftp",
            "path": "/backups",
            "host": "backup.internal",
            "username": "backup",
        },
        secret=None,
        requires_secret=True,
    )

    assert item.sync_status == "requires_secret"
    assert item.secret_envelope is None
    assert commands.created == []
    assert serialize_managed_profile(item)["requiresSecret"] is True


def test_direct_smb_destination_is_an_allowed_public_profile():
    AgentProfileService._validate(
        "destination",
        {"type": "smb_direct", "path": r"\\backup-core\RespaldosTI"},
        None,
    )
