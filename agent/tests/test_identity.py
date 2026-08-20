from __future__ import annotations

from agent.data_express_agent.identity import AgentIdentity, IdentityStore


class FakeProtector:
    def protect(self, value: bytes) -> bytes:
        return bytes(item ^ 0xA5 for item in value)

    def unprotect(self, value: bytes) -> bytes:
        return bytes(item ^ 0xA5 for item in value)


def test_identity_is_stable_and_private_key_is_not_stored_in_plaintext(tmp_path):
    path = tmp_path / "identity.json"
    store = IdentityStore(path, protector=FakeProtector())

    original = store.load_or_create()
    plaintext_key = original.private_key.private_bytes_raw()
    stored_bytes = path.read_bytes()
    loaded = store.load()

    assert plaintext_key not in stored_bytes
    assert loaded.installation_id == original.installation_id
    assert loaded.private_key.private_bytes_raw() == plaintext_key


def test_enrollment_fields_survive_an_atomic_identity_save(tmp_path):
    store = IdentityStore(tmp_path / "identity.json", protector=FakeProtector())
    identity = store.load_or_create()
    identity.agent_id = "0c76660f-033a-47de-9b68-7ec3b3fd7591"
    identity.tenant_id = "0634bcba-54b2-4d18-972c-3f64c76db51d"

    store.save(identity)
    restored = store.load()

    assert restored.agent_id == identity.agent_id
    assert restored.tenant_id == identity.tenant_id
    assert not store.path.with_suffix(".json.tmp").exists()


def test_version_one_identity_migrates_without_changing_installation_or_signing_key(tmp_path):
    path = tmp_path / "identity.json"
    protector = FakeProtector()
    original = AgentIdentity.generate()
    import base64
    import json
    from agent.data_express_agent.protocol import private_key_to_base64

    protected = protector.protect(private_key_to_base64(original.private_key).encode("ascii"))
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "installationId": original.installation_id,
                "agentId": None,
                "tenantId": None,
                "protectedPrivateKey": base64.b64encode(protected).decode("ascii"),
            }
        ),
        encoding="utf-8",
    )

    migrated = IdentityStore(path, protector=protector).load_or_create()

    assert migrated.installation_id == original.installation_id
    assert migrated.private_key.private_bytes_raw() == original.private_key.private_bytes_raw()
    assert migrated.encryption_public_key
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 2
