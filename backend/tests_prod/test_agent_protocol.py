from __future__ import annotations

import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))


def test_backend_and_agent_share_request_signature_contract():
    from app import agent_protocol as backend_protocol
    from agent.data_express_agent import protocol as windows_protocol

    private_key = _private_key()
    public_key = private_key.public_key()
    body = b'{"hostname":"CORE-01","version":"1.0.0"}'
    values = {
        "method": "POST",
        "path_with_query": "/agent/v1/heartbeat?full=false",
        "timestamp": 1_786_381_200,
        "nonce": "9a11c83152b24e22a6e2f90d254e9776",
        "body": body,
    }

    backend_signature = backend_protocol.sign_request(private_key, **values)
    agent_signature = windows_protocol.sign_request(private_key, **values)

    assert backend_signature == agent_signature
    assert backend_protocol.request_signing_message(**values) == windows_protocol.request_signing_message(**values)
    windows_protocol.verify_request(
        public_key,
        signature=backend_signature,
        now=values["timestamp"],
        **values,
    )
    backend_protocol.verify_request(
        public_key,
        signature=agent_signature,
        now=values["timestamp"],
        **values,
    )


def test_backend_and_agent_share_command_signature_contract():
    from app import agent_protocol as backend_protocol
    from agent.data_express_agent import protocol as windows_protocol

    private_key = _private_key()
    public_key = private_key.public_key()
    body = b'{"id":"command-1","type":"browse_drives"}'
    key_id = "railway-2026-01"

    signature = backend_protocol.sign_command(private_key, key_id, body)

    assert signature == windows_protocol.sign_command(private_key, key_id, body)
    windows_protocol.verify_command(public_key, key_id, body, signature)


def test_request_rejects_modified_body_expired_timestamp_and_replayed_nonce():
    from app import agent_protocol

    private_key = _private_key()
    public_key = private_key.public_key()
    values = {
        "method": "POST",
        "path_with_query": "/agent/v1/heartbeat",
        "timestamp": 1_786_381_200,
        "nonce": "unique-nonce",
        "body": b'{"status":"ok"}',
    }
    signature = agent_protocol.sign_request(private_key, **values)

    with pytest.raises(agent_protocol.AgentProtocolError) as modified:
        agent_protocol.verify_request(
            public_key,
            signature=signature,
            now=values["timestamp"],
            **{**values, "body": b'{"status":"changed"}'},
        )
    assert modified.value.code == "AGENT_SIGNATURE_INVALID"

    with pytest.raises(agent_protocol.AgentProtocolError) as expired:
        agent_protocol.verify_request(
            public_key,
            signature=signature,
            now=values["timestamp"] + 121,
            **values,
        )
    assert expired.value.code == "AGENT_TIMESTAMP_INVALID"

    with pytest.raises(agent_protocol.AgentProtocolError) as replayed:
        agent_protocol.verify_request(
            public_key,
            signature=signature,
            now=values["timestamp"],
            nonce_available=lambda _: False,
            **values,
        )
    assert replayed.value.code == "AGENT_REPLAY_DETECTED"


def test_key_serialization_round_trip_and_invalid_key_rejected():
    from app import agent_protocol

    private_key = _private_key()
    encoded_private = agent_protocol.private_key_to_base64(private_key)
    encoded_public = agent_protocol.public_key_to_base64(private_key.public_key())

    loaded_private = agent_protocol.load_private_key(encoded_private)
    loaded_public = agent_protocol.load_public_key(encoded_public)
    signature = agent_protocol.sign_command(loaded_private, "key-1", b"payload")
    agent_protocol.verify_command(loaded_public, "key-1", b"payload", signature)

    with pytest.raises(agent_protocol.AgentProtocolError) as invalid:
        agent_protocol.load_public_key("not-a-valid-key")
    assert invalid.value.code == "AGENT_KEY_INVALID"

