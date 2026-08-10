from __future__ import annotations

import time
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.agent_protocol import public_key_to_base64, sign_request
from app.core.errors import DomainError
from app.models.operations import RemoteAgent
from app.services.agent_auth_service import AgentAuthService


class FakeAuthRepo:
    def __init__(self, agent: RemoteAgent):
        self.agent = agent
        self.nonces: set[tuple[uuid.UUID, str]] = set()

    async def get_agent_unscoped(self, agent_id: str):
        return self.agent if str(self.agent.id) == agent_id else None

    async def reserve_nonce(self, agent: RemoteAgent, nonce_hash: str, expires_at):
        key = (agent.id, nonce_hash)
        if key in self.nonces:
            return False
        self.nonces.add(key)
        return True

    async def flush(self):
        return None


def _fixture():
    private_key = Ed25519PrivateKey.generate()
    agent = RemoteAgent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        installation_id=str(uuid.uuid4()),
        hostname="CORE-01",
        agent_version="0.1.0",
        public_key=public_key_to_base64(private_key.public_key()),
        status="connected",
    )
    repo = FakeAuthRepo(agent)
    return private_key, agent, repo


@pytest.mark.asyncio
async def test_signed_request_authenticates_and_nonce_cannot_be_replayed():
    private_key, agent, repo = _fixture()
    now = int(time.time())
    body = b'{"status":"ok"}'
    signature = sign_request(
        private_key,
        method="POST",
        path_with_query="/agent/v1/heartbeat",
        timestamp=now,
        nonce="one-time-nonce",
        body=body,
    )
    service = AgentAuthService(repo=repo, now=lambda: now, max_clock_skew=120)

    authenticated = await service.authenticate(
        agent_id=str(agent.id),
        timestamp=str(now),
        nonce="one-time-nonce",
        signature=signature,
        method="POST",
        path_with_query="/agent/v1/heartbeat",
        body=body,
    )

    assert authenticated is agent
    assert agent.last_seen_at is not None

    with pytest.raises(DomainError) as replay:
        await service.authenticate(
            agent_id=str(agent.id),
            timestamp=str(now),
            nonce="one-time-nonce",
            signature=signature,
            method="POST",
            path_with_query="/agent/v1/heartbeat",
            body=body,
        )
    assert replay.value.code == "AGENT_AUTH_INVALID"


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["body", "path", "expired", "revoked"])
async def test_authentication_failures_are_generic_and_do_not_reveal_reason(mutation):
    private_key, agent, repo = _fixture()
    now = int(time.time())
    timestamp = now - 300 if mutation == "expired" else now
    signed_body = b"{}"
    signature = sign_request(
        private_key,
        method="POST",
        path_with_query="/agent/v1/heartbeat",
        timestamp=timestamp,
        nonce=f"nonce-{mutation}",
        body=signed_body,
    )
    if mutation == "revoked":
        agent.status = "revoked"
    body = b'{"tampered":true}' if mutation == "body" else signed_body
    path = "/agent/v1/heartbeat?changed=1" if mutation == "path" else "/agent/v1/heartbeat"

    with pytest.raises(DomainError) as failure:
        await AgentAuthService(repo=repo, now=lambda: now).authenticate(
            agent_id=str(agent.id),
            timestamp=str(timestamp),
            nonce=f"nonce-{mutation}",
            signature=signature,
            method="POST",
            path_with_query=path,
            body=body,
        )

    assert failure.value.status_code == 401
    assert failure.value.code == "AGENT_AUTH_INVALID"
    assert "firma" not in failure.value.message.lower()

