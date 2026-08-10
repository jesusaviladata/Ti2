from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent_protocol import load_private_key, load_public_key, sign_command, verify_command
from app.core.config import Settings


def _base_values() -> dict:
    return {
        "_env_file": None,
        "SECRET_KEY": "test-secret-" + "a" * 52,
        "APP_ENV": "test",
    }


def test_agent_module_can_remain_disabled_without_signing_key():
    settings = Settings(**_base_values(), AGENT_MODULE_ENABLED=False)

    assert settings.AGENT_COMMAND_SIGNING_PRIVATE_KEY == ""


def test_agent_module_rejects_missing_or_invalid_signing_configuration():
    with pytest.raises(ValidationError):
        Settings(**_base_values(), AGENT_MODULE_ENABLED=True)

    with pytest.raises(ValidationError):
        Settings(
            **_base_values(),
            AGENT_MODULE_ENABLED=True,
            AGENT_COMMAND_SIGNING_PRIVATE_KEY="CHANGE_ME",
            AGENT_COMMAND_SIGNING_KEY_ID="bad key id",
        )


def test_generated_signing_material_is_accepted_and_cross_verifiable():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "generate_agent_signing_key.py"
    spec = importlib.util.spec_from_file_location("generate_agent_signing_key", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    material = module.generate_signing_material("railway-2026-01")
    settings = Settings(
        **_base_values(),
        AGENT_MODULE_ENABLED=True,
        AGENT_COMMAND_SIGNING_PRIVATE_KEY=material["privateKey"],
        AGENT_COMMAND_SIGNING_KEY_ID=material["keyId"],
    )

    private_key = load_private_key(settings.AGENT_COMMAND_SIGNING_PRIVATE_KEY)
    public_key = load_public_key(material["publicKey"])
    signature = sign_command(private_key, settings.AGENT_COMMAND_SIGNING_KEY_ID, b"test")
    verify_command(public_key, material["keyId"], b"test", signature)


def test_agent_timing_limits_are_bounded():
    values = _base_values()

    with pytest.raises(ValidationError):
        Settings(**values, AGENT_ENROLLMENT_TTL_SEC=86_400)
    with pytest.raises(ValidationError):
        Settings(**values, AGENT_MAX_CLOCK_SKEW_SEC=3_600)

