from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agent.data_express_agent.client import AgentClient, AgentClientError, canonical_json
from agent.data_express_agent.config import AgentConfig
from agent.data_express_agent.identity import AgentIdentity
from agent.data_express_agent.protocol import (
    public_key_to_base64,
    sign_command,
    verify_request,
)


def _config(server_private_key):
    return AgentConfig(
        server_url="https://example.test",
        command_signing_public_key=public_key_to_base64(server_private_key.public_key()),
        command_signing_key_id="railway-current",
        data_dir=None,
        poll_wait_seconds=0,
        request_timeout_seconds=10,
    )


def test_client_signs_exact_request_and_verifies_exact_command_response():
    server_private_key = Ed25519PrivateKey.generate()
    identity = AgentIdentity.generate()
    identity.agent_id = str(uuid.uuid4())
    identity.tenant_id = str(uuid.uuid4())
    command = {
        "id": str(uuid.uuid4()),
        "agentId": identity.agent_id,
        "tenantId": identity.tenant_id,
        "type": "browse_drives",
        "payload": {},
        "configRevision": 0,
        "issuedAt": datetime.now(timezone.utc).isoformat(),
        "expiresAt": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(),
        "idempotencyKey": "browse-1",
    }
    response_body = canonical_json(command)

    def handler(request: httpx.Request):
        assert request.url.raw_path == b"/agent/v1/commands/next?wait=0"
        verify_request(
            identity.private_key.public_key(),
            signature=request.headers["X-Agent-Signature"],
            method=request.method,
            path_with_query=request.url.raw_path.decode("ascii"),
            timestamp=int(request.headers["X-Agent-Timestamp"]),
            nonce=request.headers["X-Agent-Nonce"],
            body=request.content,
            now=int(time.time()),
        )
        return httpx.Response(
            200,
            content=response_body,
            headers={
                "X-Command-Key-Id": "railway-current",
                "X-Command-Signature": sign_command(
                    server_private_key, "railway-current", response_body
                ),
            },
        )

    client = AgentClient(
        _config(server_private_key),
        identity,
        transport=httpx.MockTransport(handler),
    )
    assert client.next_command() == command
    client.close()


def test_client_rejects_tampered_command_before_parsing_or_execution():
    server_private_key = Ed25519PrivateKey.generate()
    identity = AgentIdentity.generate()
    identity.agent_id = str(uuid.uuid4())
    identity.tenant_id = str(uuid.uuid4())
    signed = b'{"type":"browse_drives"}'
    signature = sign_command(server_private_key, "railway-current", signed)

    def handler(_request):
        return httpx.Response(
            200,
            content=b'{"type":"purge_quarantine_items"}',
            headers={
                "X-Command-Key-Id": "railway-current",
                "X-Command-Signature": signature,
            },
        )

    client = AgentClient(
        _config(server_private_key), identity, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(AgentClientError) as rejected:
        client.next_command()
    assert rejected.value.code == "COMMAND_SIGNATURE_INVALID"
    client.close()


def test_enrollment_sends_public_identity_and_accepts_only_expected_key_id():
    server_private_key = Ed25519PrivateKey.generate()
    identity = AgentIdentity.generate()
    agent_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())

    def handler(request):
        body = json.loads(request.content)
        assert body["installationId"] == identity.installation_id
        assert body["publicKey"] == identity.public_key
        assert body["pairingCode"] == "PAIR-CODE"
        return httpx.Response(
            201,
            json={
                "agentId": agent_id,
                "tenantId": tenant_id,
                "commandSigningKeyId": "railway-current",
            },
        )

    client = AgentClient(
        _config(server_private_key), identity, transport=httpx.MockTransport(handler)
    )
    client.enroll("PAIR-CODE", hostname="CORE-01", os_version="Windows Server 2022")
    assert identity.agent_id == agent_id
    assert identity.tenant_id == tenant_id
    client.close()

