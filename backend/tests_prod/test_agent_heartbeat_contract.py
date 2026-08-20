from datetime import datetime, timezone
import base64

import pytest
from pydantic import ValidationError

from app.schemas.agent import AgentHeartbeatRequest


def test_legacy_030_heartbeat_remains_valid():
    body = AgentHeartbeatRequest.model_validate(
        {
            "agentVersion": "0.3.0",
            "metadata": {"hostname": "CORE-01", "sqlInstances": ["MSSQLSERVER"]},
        }
    )

    assert body.agent_version == "0.3.0"
    assert body.health is None
    assert body.volumes == []


def test_040_heartbeat_accepts_health_and_bounded_volume_telemetry():
    observed_at = datetime.now(timezone.utc)
    body = AgentHeartbeatRequest.model_validate(
        {
            "agentVersion": "0.4.0",
            "health": {
                "status": "busy",
                "currentOperation": "backup",
                "appliedConfigRevision": 4,
            },
            "volumes": [
                {
                    "volumeKey": "D:",
                    "label": "Data",
                    "mountPoint": "D:\\",
                    "totalBytes": 3_400_000_000_000,
                    "freeBytes": 2_200_000_000_000,
                    "usedPercent": 35.3,
                    "roles": ["backup", "destination"],
                    "observedAt": observed_at.isoformat(),
                }
            ],
        }
    )

    assert body.health.status == "busy"
    assert body.volumes[0].volume_key == "D:"
    assert body.volumes[0].roles == ["backup", "destination"]


def test_041_heartbeat_accepts_agent_encryption_public_key():
    public_key = base64.b64encode(b"k" * 32).decode("ascii")
    body = AgentHeartbeatRequest.model_validate(
        {"agentVersion": "0.4.1", "encryptionPublicKey": public_key}
    )

    assert body.encryption_public_key == public_key


@pytest.mark.parametrize(
    "volume_patch",
    [
        {"freeBytes": -1},
        {"usedPercent": 101},
        {"roles": ["database"]},
        {"totalBytes": 10, "freeBytes": 11},
    ],
)
def test_heartbeat_rejects_invalid_volume_telemetry(volume_patch):
    volume = {
        "volumeKey": "D:",
        "mountPoint": "D:\\",
        "totalBytes": 100,
        "freeBytes": 20,
        "usedPercent": 80,
        "roles": ["backup"],
        "observedAt": datetime.now(timezone.utc).isoformat(),
    }
    volume.update(volume_patch)

    with pytest.raises(ValidationError):
        AgentHeartbeatRequest.model_validate({"volumes": [volume]})


@pytest.mark.parametrize("secret_key", ["password", "connectionString", "private_key"])
def test_heartbeat_rejects_secrets_in_public_metadata(secret_key):
    with pytest.raises(ValidationError):
        AgentHeartbeatRequest.model_validate(
            {"metadata": {"nested": {secret_key: "must-not-leave-agent"}}}
        )
