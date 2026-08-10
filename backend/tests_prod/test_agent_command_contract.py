from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.agent_protocol import private_key_to_base64, verify_command
from app.api.agent import _command_response
from app.core.config import settings
from app.main import app
from app.models.operations import AgentCommand


def test_agent_command_routes_are_outside_cookie_api_namespace():
    paths = {route.path for route in app.routes}
    assert "/agent/v1/commands/next" in paths
    assert "/agent/v1/commands/{command_id}/progress" in paths
    assert "/agent/v1/commands/{command_id}/complete" in paths
    assert "/agent/v1/commands/{command_id}/fail" in paths
    assert "/agent/v1/heartbeat" in paths


def test_command_response_signs_the_exact_bytes_sent(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(
        settings,
        "AGENT_COMMAND_SIGNING_PRIVATE_KEY",
        private_key_to_base64(private_key),
    )
    monkeypatch.setattr(settings, "AGENT_COMMAND_SIGNING_KEY_ID", "railway-2026-01")
    now = datetime.now(timezone.utc)
    command = AgentCommand(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        command_type="browse_drives",
        payload={},
        payload_hash="0" * 64,
        status="claimed",
        idempotency_key="browse-1",
        created_at=now,
        expires_at=now + timedelta(minutes=2),
    )

    response = _command_response(command)

    assert response.headers["cache-control"] == "no-store"
    verify_command(
        private_key.public_key(),
        response.headers["x-command-key-id"],
        response.body,
        response.headers["x-command-signature"],
    )

