from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agent.data_express_agent.bootstrap import (
    AgentBootstrap,
    AgentBootstrapError,
    CommandTrust,
    PairingCodeFile,
)
from agent.data_express_agent.config import AgentConfig
from agent.data_express_agent.protocol import (
    public_key_to_base64,
    sign_command,
)


def _document(private_key, *, url="https://agente.dataexpress.test"):
    return {
        "schemaVersion": 1,
        "controlPlaneUrl": url,
        "agentVersion": "0.5.0",
        "commandTrust": {
            "activeKeyId": "package-current",
            "keys": [
                {
                    "keyId": "package-current",
                    "publicKey": public_key_to_base64(private_key.public_key()),
                }
            ],
        },
    }


def test_bootstrap_requires_https_domain_and_valid_packaged_trust(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    path = tmp_path / "bootstrap.json"
    path.write_text(json.dumps(_document(private_key)), encoding="utf-8")

    bootstrap = AgentBootstrap.from_file(path)

    assert bootstrap.control_plane_url == "https://agente.dataexpress.test"
    assert bootstrap.command_trust.active_key_id == "package-current"

    path.write_text(
        json.dumps(_document(private_key, url="http://temporary.example/path")),
        encoding="utf-8",
    )
    with pytest.raises(AgentBootstrapError):
        AgentBootstrap.from_file(path)


def test_runtime_can_start_without_profiles_and_imports_legacy_public_profiles(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    bootstrap_path = tmp_path / "bootstrap.json"
    bootstrap_path.write_text(json.dumps(_document(private_key)), encoding="utf-8")
    bootstrap = AgentBootstrap.from_file(bootstrap_path)

    empty = AgentConfig.from_bootstrap(bootstrap)
    assert empty.sql_instances == ()
    assert empty.backup_destinations == ()

    legacy_path = tmp_path / "agent.json"
    legacy_path.write_text(
        json.dumps(
            {
                "serverUrl": "https://untrusted-host.example",
                "commandSigningPublicKey": "untrusted",
                "commandSigningKeyId": "untrusted",
                "verifyTls": False,
                "dataDir": str(tmp_path / "data"),
                "sqlInstances": [{"id": "sql", "label": "SQL heredado"}],
                "backupDestinations": [
                    {"id": "dest", "label": "Destino heredado", "type": "local"}
                ],
            }
        ),
        encoding="utf-8",
    )
    migrated = AgentConfig.from_bootstrap(bootstrap, legacy_path)
    assert migrated.server_url == bootstrap.control_plane_url
    assert migrated.verify_tls is True
    assert migrated.sql_instances[0]["id"] == "sql"
    assert migrated.backup_destinations[0]["id"] == "dest"


def test_command_trust_rotation_must_be_signed_by_current_trust():
    current = Ed25519PrivateKey.generate()
    next_key = Ed25519PrivateKey.generate()
    trust = CommandTrust.from_document(_document(current)["commandTrust"])
    payload = {
        "schemaVersion": 1,
        "activeKeyId": "next",
        "keys": [
            {
                "keyId": "next",
                "publicKey": public_key_to_base64(next_key.public_key()),
            }
        ],
    }
    body = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    rotation = {
        **payload,
        "signedBy": "package-current",
        "signature": sign_command(current, "package-current", body),
    }

    rotated = trust.apply_signed_rotation(rotation)
    assert rotated.active_key_id == "next"

    rotation["activeKeyId"] = "tampered"
    with pytest.raises(AgentBootstrapError):
        trust.apply_signed_rotation(rotation)


def test_pairing_code_file_is_removed_when_consumed(tmp_path):
    path = tmp_path / "pairing-code.tmp"
    path.write_text("ONE-TIME-CODE", encoding="utf-8")

    assert PairingCodeFile(path).consume() == "ONE-TIME-CODE"
    assert not path.exists()


def test_pairing_code_can_be_read_without_deleting_during_recoverable_retry(tmp_path):
    path = tmp_path / "pairing-code.tmp"
    path.write_text("RETRY-CODE", encoding="utf-8")
    pairing = PairingCodeFile(path)

    assert pairing.read() == "RETRY-CODE"
    assert path.exists()
    pairing.delete()
    assert not path.exists()
