import base64
import json

import pytest

from agent.data_express_agent.identity import AgentIdentity
from agent.data_express_agent.profiles import ManagedProfileStore, ProfileApplyError
from agent.data_express_agent.secrets import seal_secret_envelope


class FakeProtector:
    def protect(self, value: bytes) -> bytes:
        return bytes(item ^ 0x5A for item in value)

    def unprotect(self, value: bytes) -> bytes:
        return bytes(item ^ 0x5A for item in value)


def _payload(identity, profile_id, revision=1):
    envelope = seal_secret_envelope(
        identity.encryption_private_key.public_key(),
        {"privateKey": "PRIVATE MATERIAL"},
        context=f"{identity.agent_id}:{profile_id}".encode("ascii"),
    )
    return {
        "configRevision": revision,
        "profiles": [
            {
                "id": profile_id,
                "profileType": "destination",
                "profileKey": "central",
                "label": "Servidor central",
                "publicConfig": {
                    "type": "sftp",
                    "path": "/backups",
                    "host": "backup.internal",
                    "username": "backup",
                },
                "secretEnvelope": envelope,
                "desiredRevision": revision,
                "isActive": True,
            }
        ],
    }


def test_profile_application_is_atomic_monotonic_and_secret_is_protected(tmp_path):
    identity = AgentIdentity.generate()
    identity.agent_id = "0c76660f-033a-47de-9b68-7ec3b3fd7591"
    profile_id = "0634bcba-54b2-4d18-972c-3f64c76db51d"
    path = tmp_path / "managed-profiles.json"
    store = ManagedProfileStore(path, identity, protector=FakeProtector())

    result = store.apply(_payload(identity, profile_id))

    assert result["status"] == "applied"
    assert b"PRIVATE MATERIAL" not in path.read_bytes()
    _sql, destinations = store.runtime_profiles()
    assert destinations[0]["privateKey"] == "PRIVATE MATERIAL"
    assert not path.with_suffix(".json.tmp").exists()

    with pytest.raises(ProfileApplyError) as stale:
        store.apply({"configRevision": 0, "profiles": []})
    assert stale.value.code == "PROFILE_REVISION_STALE"


def test_profile_envelope_for_another_agent_does_not_replace_last_good_config(tmp_path):
    target = AgentIdentity.generate()
    target.agent_id = "0c76660f-033a-47de-9b68-7ec3b3fd7591"
    other = AgentIdentity.generate()
    other.agent_id = target.agent_id
    profile_id = "0634bcba-54b2-4d18-972c-3f64c76db51d"
    path = tmp_path / "managed-profiles.json"
    store = ManagedProfileStore(path, target, protector=FakeProtector())
    store.apply(_payload(target, profile_id, 1))
    previous = path.read_bytes()

    with pytest.raises(ValueError):
        store.apply(_payload(other, profile_id, 2))

    assert path.read_bytes() == previous
