from __future__ import annotations

from sqlalchemy import UniqueConstraint

from app.models.operations import (
    AgentConnectionProfile,
    AgentCommand,
    AgentPairingToken,
    AgentRequestNonce,
    AgentStorageAlert,
    AgentVolumeState,
    RemoteAgent,
    RemoteServer,
    RemoteStructureValidation,
)


def _unique_column_sets(model) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_agent_tables_are_tenant_scoped():
    for model in (
        RemoteAgent,
        AgentPairingToken,
        AgentCommand,
        AgentRequestNonce,
        RemoteStructureValidation,
    ):
        assert "tenant_id" in model.__table__.columns
        assert model.__table__.columns["tenant_id"].nullable is False


def test_agent_installation_nonce_and_command_idempotency_are_unique():
    assert ("tenant_id", "installation_id") in _unique_column_sets(RemoteAgent)
    assert ("agent_id", "nonce_hash") in _unique_column_sets(AgentRequestNonce)
    assert ("agent_id", "idempotency_key") in _unique_column_sets(AgentCommand)
    assert ("token_hash",) in _unique_column_sets(AgentPairingToken)


def test_remote_server_supports_agent_and_legacy_transports():
    columns = RemoteServer.__table__.columns

    assert columns["transport"].nullable is False
    assert columns["agent_id"].nullable is True
    assert columns["protocol"].nullable is True
    assert columns["host"].nullable is True
    assert columns["port"].nullable is True
    assert columns["username"].nullable is True
    assert columns["target_folders"].nullable is False
    assert columns["target_files"].nullable is False
    assert columns["config_revision"].nullable is False
    assert columns["configuration_hash"].nullable is True
    assert columns["validated_at"].nullable is True


def test_agent_commands_have_durable_lifecycle_fields():
    columns = AgentCommand.__table__.columns

    for name in (
        "agent_id",
        "job_id",
        "command_type",
        "payload",
        "payload_hash",
        "status",
        "idempotency_key",
        "expires_at",
        "claimed_at",
        "completed_at",
        "result_summary",
        "error_code",
        "error_message",
    ):
        assert name in columns


def test_remote_agent_tracks_encryption_heartbeat_and_configuration_revisions():
    columns = RemoteAgent.__table__.columns

    for name in (
        "encryption_public_key",
        "last_heartbeat_at",
        "desired_config_revision",
        "applied_config_revision",
        "health_status",
    ):
        assert name in columns

    assert columns["encryption_public_key"].nullable is True
    assert columns["last_heartbeat_at"].nullable is True
    assert columns["desired_config_revision"].nullable is False
    assert columns["applied_config_revision"].nullable is False
    assert columns["health_status"].nullable is False


def test_agent_volume_state_is_unique_per_agent_volume():
    columns = AgentVolumeState.__table__.columns

    assert ("tenant_id", "agent_id", "volume_key") in _unique_column_sets(
        AgentVolumeState
    )
    for name in (
        "label",
        "mount_point",
        "total_bytes",
        "free_bytes",
        "used_percent",
        "roles",
        "observed_at",
        "error",
    ):
        assert name in columns


def test_agent_storage_alert_has_durable_open_and_resolution_state():
    columns = AgentStorageAlert.__table__.columns

    for name in (
        "agent_id",
        "volume_key",
        "severity",
        "status",
        "free_bytes",
        "total_bytes",
        "free_percent",
        "thresholds",
        "opened_at",
        "last_observed_at",
        "resolved_at",
    ):
        assert name in columns


def test_agent_connection_profiles_are_revisioned_and_tenant_scoped():
    columns = AgentConnectionProfile.__table__.columns

    assert ("tenant_id", "agent_id", "profile_type", "profile_key") in _unique_column_sets(
        AgentConnectionProfile
    )
    for name in (
        "public_config",
        "secret_envelope",
        "desired_revision",
        "applied_revision",
        "sync_status",
        "last_test_status",
        "last_test_at",
        "last_error",
        "is_active",
    ):
        assert name in columns
