from __future__ import annotations

from agent.data_express_agent.identity import IdentityStore


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

