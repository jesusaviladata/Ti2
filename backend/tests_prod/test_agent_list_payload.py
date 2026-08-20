from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.api.v1.agents import _serialize
from app.models.operations import RemoteAgent


def test_agent_list_payload_exposes_frontend_selection_fields():
    agent = RemoteAgent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        installation_id=str(uuid.uuid4()),
        hostname="CORE-01",
        os_version="Windows Server 2022",
        agent_version="0.3.0",
        public_key="test-public-key",
        status="connected",
        last_seen_at=datetime.now(timezone.utc),
        last_heartbeat_at=datetime.now(timezone.utc),
        health_status="busy",
        metadata_json={"sqlInstances": [{"id": "main"}]},
    )

    payload = _serialize(agent)

    assert payload["online"] is True
    assert payload["healthStatus"] == "busy"
    assert payload["lastHeartbeatAt"] is not None
    assert payload["metadata"] == {"sqlInstances": [{"id": "main"}]}
    assert payload["configuration"] is None
