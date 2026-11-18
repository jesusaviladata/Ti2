from __future__ import annotations

import json
import re
import uuid
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_protocol import (
    load_public_key,
    private_key_to_base64,
    sign_command,
    verify_command,
)
from app.api.v1 import agent_module as agent_module_api
from app.core.config import Settings, settings
from app.core.database import get_db
from app.core.errors import DomainError, domain_error_handler
from app.models.agent_module import AgentModuleSetting
from app.models.user import User, UserRole
from app.services import agent_module


SECRET = "test-secret-" + "a" * 52
OTHER_SECRET = "other-secret-" + "b" * 52


def _config(**overrides) -> Settings:
    values = {"_env_file": None, "SECRET_KEY": SECRET, "APP_ENV": "test"}
    values.update(overrides)
    return Settings(**values)


def _stored_row(*, enabled: bool, secret: str = SECRET) -> tuple[AgentModuleSetting, Ed25519PrivateKey]:
    private_key = Ed25519PrivateKey.generate()
    key_id = "panel-20261118-abc123"
    row = AgentModuleSetting(
        id=1,
        enabled=enabled,
        signing_key_id=key_id,
        signing_public_key=agent_module.public_key_to_base64(private_key.public_key()),
        signing_private_key_encrypted=agent_module.encrypt_private_key(private_key, key_id, secret),
    )
    return row, private_key


class FakeSession:
    def __init__(self, row: AgentModuleSetting | None = None):
        self.row = row
        self.commits = 0

    async def execute(self, statement):
        if getattr(statement, "is_insert", False):
            if self.row is None:
                self.row = AgentModuleSetting(id=1, enabled=False)
            return None
        return SimpleNamespace(scalar_one_or_none=lambda: self.row)

    async def commit(self):
        self.commits += 1


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    saved = agent_module.current()
    monkeypatch.setattr(settings, "AGENT_MODULE_ENABLED", False)
    monkeypatch.setattr(settings, "AGENT_MODULE_SELF_SERVICE", True)
    monkeypatch.setattr(settings, "AGENT_COMMAND_SIGNING_PRIVATE_KEY", "")
    monkeypatch.setattr(settings, "AGENT_COMMAND_SIGNING_KEY_ID", "")
    monkeypatch.setattr(settings, "AGENT_CONTROL_PLANE_URL", "")
    monkeypatch.setattr(settings, "APP_ORIGIN", "https://panel.example.com")
    monkeypatch.setattr(settings, "SECRET_KEY", SECRET)
    agent_module._publish(agent_module.resolve_state(None))
    yield
    agent_module._publish(saved)


# ----------------------------------------------------------------- custodia


def test_private_key_round_trips_through_encryption():
    private_key = Ed25519PrivateKey.generate()
    envelope = agent_module.encrypt_private_key(private_key, "panel-1", SECRET)

    restored = agent_module.decrypt_private_key(envelope, "panel-1", SECRET)

    assert private_key_to_base64(restored) == private_key_to_base64(private_key)
    assert private_key_to_base64(private_key) not in envelope


def test_encrypted_key_is_bound_to_secret_and_key_id():
    envelope = agent_module.encrypt_private_key(Ed25519PrivateKey.generate(), "panel-1", SECRET)

    with pytest.raises(ValueError):
        agent_module.decrypt_private_key(envelope, "panel-1", OTHER_SECRET)
    with pytest.raises(ValueError):
        agent_module.decrypt_private_key(envelope, "panel-2", SECRET)


def test_generated_key_ids_are_valid_for_the_agent_protocol():
    key_id = agent_module.new_key_id()

    assert re.fullmatch(r"panel-\d{8}-[0-9a-f]{6}", key_id)
    assert len(key_id) <= 64


# ----------------------------------------------------------------- estado efectivo


def test_fresh_installation_starts_disabled_and_manageable_from_panel():
    state = agent_module.resolve_state(None, _config())

    assert (state.enabled, state.managed_by, state.key_status) == (False, "panel", "missing")


def test_panel_enabled_row_with_readable_key_enables_the_module():
    row, private_key = _stored_row(enabled=True)

    state = agent_module.resolve_state(row, _config())

    assert state.enabled is True
    assert state.key_source == "database"
    assert private_key_to_base64(state.private_key) == private_key_to_base64(private_key)


def test_unreadable_key_fails_closed_even_if_panel_wants_it_on():
    row, _ = _stored_row(enabled=True, secret=OTHER_SECRET)

    state = agent_module.resolve_state(row, _config())

    assert state.enabled is False
    assert state.key_status == "unreadable"
    assert state.private_key is None


def test_disabled_row_keeps_its_key_for_the_next_activation():
    row, _ = _stored_row(enabled=False)

    state = agent_module.resolve_state(row, _config())

    assert state.enabled is False
    assert state.key_status == "ok"


def test_environment_can_force_the_module_on():
    private_key = Ed25519PrivateKey.generate()
    config = _config(
        AGENT_MODULE_ENABLED=True,
        AGENT_COMMAND_SIGNING_PRIVATE_KEY=private_key_to_base64(private_key),
        AGENT_COMMAND_SIGNING_KEY_ID="railway-2026-11",
    )

    state = agent_module.resolve_state(None, config)

    assert (state.enabled, state.managed_by, state.key_source) == (True, "server", "environment")


def test_environment_can_forbid_panel_activation():
    row, _ = _stored_row(enabled=True)

    state = agent_module.resolve_state(row, _config(AGENT_MODULE_SELF_SERVICE=False))

    assert (state.enabled, state.managed_by) == (False, "locked")


def test_environment_key_takes_precedence_over_the_stored_key():
    row, _ = _stored_row(enabled=True)
    env_key = Ed25519PrivateKey.generate()
    config = _config(
        AGENT_COMMAND_SIGNING_PRIVATE_KEY=private_key_to_base64(env_key),
        AGENT_COMMAND_SIGNING_KEY_ID="external-key",
    )

    state = agent_module.resolve_state(row, config)

    assert (state.enabled, state.key_source, state.key_id) == (True, "environment", "external-key")


def test_misconfigured_environment_key_fails_at_startup():
    with pytest.raises(ValueError):
        _config(AGENT_COMMAND_SIGNING_PRIVATE_KEY="CHANGE_ME", AGENT_COMMAND_SIGNING_KEY_ID="x")


@pytest.mark.parametrize(
    "url",
    ["ftp://panel.example.com", "https://panel.example.com/agentes", "https://panel.example.com?x=1"],
)
def test_control_plane_url_must_be_a_bare_origin(url):
    with pytest.raises(ValueError):
        _config(AGENT_CONTROL_PLANE_URL=url)


def test_route_guard_follows_the_published_state():
    with pytest.raises(DomainError) as error:
        agent_module.require_enabled()
    assert error.value.code == "AGENT_MODULE_DISABLED"

    row, _ = _stored_row(enabled=True)
    agent_module._publish(agent_module.resolve_state(row))

    agent_module.require_enabled()


# ----------------------------------------------------------------- activacion


@pytest.mark.asyncio
async def test_first_activation_generates_and_encrypts_a_key():
    db = FakeSession()

    state = await agent_module.set_enabled(db, enabled=True, actor_id=uuid.uuid4())

    assert state.enabled is True and state.key_source == "database"
    assert db.commits == 1
    assert db.row.signing_private_key_encrypted.startswith("v1.")
    assert private_key_to_base64(state.private_key) not in db.row.signing_private_key_encrypted
    assert agent_module.is_enabled() is True


@pytest.mark.asyncio
async def test_turning_off_and_on_keeps_the_same_key_so_installed_agents_keep_working():
    db = FakeSession()
    first = await agent_module.set_enabled(db, enabled=True, actor_id=None)

    off = await agent_module.set_enabled(db, enabled=False, actor_id=None)
    assert off.enabled is False and agent_module.is_enabled() is False

    again = await agent_module.set_enabled(db, enabled=True, actor_id=None)
    assert again.enabled is True
    assert again.key_id == first.key_id
    assert again.public_key == first.public_key


@pytest.mark.asyncio
async def test_panel_cannot_change_a_server_managed_module(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_MODULE_ENABLED", True)

    with pytest.raises(DomainError) as error:
        await agent_module.set_enabled(FakeSession(), enabled=False, actor_id=None)

    assert error.value.code == "AGENT_MODULE_SERVER_MANAGED"


@pytest.mark.asyncio
async def test_panel_cannot_enable_when_self_service_is_disabled(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_MODULE_SELF_SERVICE", False)

    with pytest.raises(DomainError) as error:
        await agent_module.set_enabled(FakeSession(), enabled=True, actor_id=None)

    assert error.value.code == "AGENT_MODULE_SELF_SERVICE_DISABLED"


@pytest.mark.asyncio
async def test_activation_refuses_an_unreadable_stored_key():
    row, _ = _stored_row(enabled=False, secret=OTHER_SECRET)
    db = FakeSession(row)

    with pytest.raises(DomainError) as error:
        await agent_module.set_enabled(db, enabled=True, actor_id=None)

    assert error.value.code == "AGENT_SIGNING_KEY_UNREADABLE"
    assert db.commits == 0


# ----------------------------------------------------------------- bootstrap


@pytest.mark.asyncio
async def test_bootstrap_matches_the_package_schema_and_verifies_signed_commands():
    await agent_module.set_enabled(FakeSession(), enabled=True, actor_id=None)

    document = agent_module.bootstrap_document(agent_module.current())

    assert document["schemaVersion"] == 1
    assert document["controlPlaneUrl"] == "https://panel.example.com"
    trust = document["commandTrust"]
    assert trust["activeKeyId"] == trust["keys"][0]["keyId"]

    key_id, private_key = agent_module.signing_material()
    signature = sign_command(private_key, key_id, b'{"type":"heartbeat"}')
    verify_command(
        load_public_key(trust["keys"][0]["publicKey"]),
        trust["activeKeyId"],
        b'{"type":"heartbeat"}',
        signature,
    )


def test_bootstrap_requires_an_enabled_module():
    with pytest.raises(DomainError) as error:
        agent_module.bootstrap_document(agent_module.current())

    assert error.value.code == "AGENT_MODULE_DISABLED"


@pytest.mark.asyncio
async def test_bootstrap_refuses_plain_http(monkeypatch):
    monkeypatch.setattr(settings, "APP_ORIGIN", "http://localhost:3000")
    await agent_module.set_enabled(FakeSession(), enabled=True, actor_id=None)

    with pytest.raises(DomainError) as error:
        agent_module.bootstrap_document(agent_module.current())

    assert error.value.code == "AGENT_CONTROL_PLANE_INSECURE"


# ----------------------------------------------------------------- API


def _client(role: UserRole, db: FakeSession) -> TestClient:
    user = User(id=uuid.uuid4(), role=role)
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(agent_module_api.router, prefix="/api/v1/agent-module")

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[agent_module_api.read_status] = lambda: user
    if role == UserRole.admin:
        app.dependency_overrides[agent_module_api.manage_config] = lambda: user
    return TestClient(app)


def test_admin_can_enable_disable_and_download_bootstrap():
    db = FakeSession()
    client = _client(UserRole.admin, db)

    assert client.get("/api/v1/agent-module").json()["canManage"] is True

    enabled = client.put("/api/v1/agent-module", json={"enabled": True})
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert "privateKey" not in json.dumps(enabled.json())

    download = client.get("/api/v1/agent-module/bootstrap")
    assert download.status_code == 200
    assert download.headers["content-disposition"] == 'attachment; filename="bootstrap.json"'
    assert download.json()["commandTrust"]["activeKeyId"] == enabled.json()["keyId"]

    disabled = client.put("/api/v1/agent-module", json={"enabled": False})
    assert disabled.json()["enabled"] is False
    assert client.get("/api/v1/agent-module/bootstrap").status_code == 503


def test_operator_sees_status_but_cannot_manage_it():
    client = _client(UserRole.technician, FakeSession())

    body = client.get("/api/v1/agent-module").json()

    assert body["canManage"] is False
    assert body["enabled"] is False


def test_unknown_fields_are_rejected():
    client = _client(UserRole.admin, FakeSession())

    response = client.put("/api/v1/agent-module", json={"enabled": True, "privateKey": "x"})

    assert response.status_code == 422
