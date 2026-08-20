from __future__ import annotations

import uuid
import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.agent_protocol import public_key_to_base64
from app.core.errors import ConflictError, DomainError
from app.models.operations import AgentPairingToken, RemoteAgent
from app.services.agent_enrollment_service import AgentEnrollmentService


class FakeDb:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid.uuid4()


class FakeRepo:
    def __init__(self):
        self.tokens: dict[str, AgentPairingToken] = {}
        self.agents: dict[tuple[str, str], RemoteAgent] = {}
        self.by_id: dict[str, RemoteAgent] = {}

    async def get_pairing_for_update(self, token_hash: str):
        return self.tokens.get(token_hash)

    async def get_by_installation(self, tenant_id: str, installation_id: str):
        return self.agents.get((tenant_id, installation_id))

    async def get_agent(self, tenant_id: str, agent_id: str):
        agent = self.by_id.get(agent_id)
        if agent and str(agent.tenant_id) == tenant_id:
            return agent
        return None


def _public_key() -> str:
    return public_key_to_base64(Ed25519PrivateKey.generate().public_key())


@pytest.mark.asyncio
async def test_pairing_code_is_high_entropy_one_time_value_and_only_hash_is_stored():
    db = FakeDb()
    repo = FakeRepo()
    service = AgentEnrollmentService(db, repo=repo, enrollment_ttl_seconds=600)
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    result = await service.issue_pairing_code(tenant_id, user_id)
    stored = db.added[-1]

    assert result["code"].count("-") == 3
    assert len(result["code"].replace("-", "")) >= 26
    assert stored.token_hash != result["code"]
    assert len(stored.token_hash) == 64
    assert stored.created_by == uuid.UUID(user_id)


@pytest.mark.asyncio
async def test_enrollment_consumes_token_and_rejects_reuse_with_generic_error():
    db = FakeDb()
    repo = FakeRepo()
    service = AgentEnrollmentService(db, repo=repo)
    tenant_id = uuid.uuid4()
    token = AgentPairingToken(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        token_hash=service.hash_pairing_code("ABCD-EFGH-IJKL-MNOP"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    repo.tokens[token.token_hash] = token

    agent = await service.enroll(
        "ABCD-EFGH-IJKL-MNOP",
        installation_id=str(uuid.uuid4()),
        hostname="CORE-01",
        os_version="Windows Server 2022",
        agent_version="0.1.0",
        public_key=_public_key(),
    )

    assert agent.tenant_id == tenant_id
    assert token.used_at is not None

    with pytest.raises(DomainError) as reused:
        await service.enroll(
            "ABCD-EFGH-IJKL-MNOP",
            installation_id=str(uuid.uuid4()),
            hostname="CORE-02",
            os_version="Windows Server 2022",
            agent_version="0.1.0",
            public_key=_public_key(),
        )
    assert reused.value.code == "AGENT_ENROLLMENT_INVALID"
    assert "usado" not in reused.value.message.lower()


@pytest.mark.asyncio
async def test_enrollment_accepts_optional_x25519_public_key_without_breaking_030():
    db = FakeDb()
    repo = FakeRepo()
    service = AgentEnrollmentService(db, repo=repo)
    tenant_id = uuid.uuid4()
    code = "ENCR-YPTI-ONKE-Y123"
    token = AgentPairingToken(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        token_hash=service.hash_pairing_code(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    repo.tokens[token.token_hash] = token
    encryption_public_key = base64.b64encode(bytes(range(32))).decode("ascii")

    agent = await service.enroll(
        code,
        installation_id=str(uuid.uuid4()),
        hostname="CORE-01",
        os_version="Windows Server 2022",
        agent_version="0.4.0",
        public_key=_public_key(),
        encryption_public_key=encryption_public_key,
    )

    assert agent.encryption_public_key == encryption_public_key



@pytest.mark.asyncio
async def test_replacement_revokes_old_identity_and_links_new_agent():
    db = FakeDb()
    repo = FakeRepo()
    service = AgentEnrollmentService(db, repo=repo)
    tenant_id = uuid.uuid4()
    old = RemoteAgent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        installation_id=str(uuid.uuid4()),
        hostname="CORE-01",
        agent_version="0.0.9",
        public_key=_public_key(),
        status="connected",
    )
    repo.by_id[str(old.id)] = old
    code = "WXYZ-ABCD-EFGH-IJKL"
    token = AgentPairingToken(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        token_hash=service.hash_pairing_code(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        replace_agent_id=old.id,
    )
    repo.tokens[token.token_hash] = token

    new = await service.enroll(
        code,
        installation_id=str(uuid.uuid4()),
        hostname="CORE-01",
        os_version="Windows Server 2022",
        agent_version="0.1.0",
        public_key=_public_key(),
    )

    assert old.status == "revoked"
    assert old.revoked_at is not None
    assert old.replaced_by_id == new.id


@pytest.mark.asyncio
async def test_duplicate_active_installation_is_rejected():
    db = FakeDb()
    repo = FakeRepo()
    service = AgentEnrollmentService(db, repo=repo)
    tenant_id = uuid.uuid4()
    installation_id = str(uuid.uuid4())
    repo.agents[(str(tenant_id), installation_id)] = RemoteAgent(
        tenant_id=tenant_id,
        installation_id=installation_id,
        hostname="CORE-01",
        agent_version="0.1.0",
        public_key=_public_key(),
        status="connected",
    )
    code = "QRST-UVWX-YZAB-CDEF"
    token = AgentPairingToken(
        tenant_id=tenant_id,
        token_hash=service.hash_pairing_code(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    repo.tokens[token.token_hash] = token

    with pytest.raises(ConflictError) as duplicate:
        await service.enroll(
            code,
            installation_id=installation_id,
            hostname="CORE-01",
            os_version="Windows Server 2022",
            agent_version="0.1.0",
            public_key=_public_key(),
        )
    assert duplicate.value.code == "AGENT_ALREADY_ENROLLED"
