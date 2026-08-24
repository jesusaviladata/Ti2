from __future__ import annotations

import enum

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.core.database import Base
from app.models.file_backup import (
    FileBackupArtifact,
    FileBackupChain,
    FileBackupFilter,
    FileBackupFilterKind,
    FileBackupFilterOperator,
    FileBackupFormat,
    FileBackupRun,
    FileBackupRunStatus,
    FileBackupSource,
    FileBackupStrategy,
    FileBackupTask,
    FileRestoreConfirmation,
    FileRestoreJob,
)


MODELS = (
    FileBackupTask,
    FileBackupSource,
    FileBackupFilter,
    FileBackupRun,
    FileBackupChain,
    FileBackupArtifact,
    FileRestoreJob,
    FileRestoreConfirmation,
)


def _unique_column_sets(model) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _composite_foreign_keys(model) -> set[tuple[tuple[str, ...], str]]:
    return {
        (
            tuple(element.parent.name for element in constraint.elements),
            constraint.referred_table.name,
        )
        for constraint in model.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and len(constraint.elements) > 1
    }


def test_file_backup_models_are_tenant_scoped():
    for model in MODELS:
        columns = model.__table__.columns
        assert columns["tenant_id"].nullable is False
        assert columns["created_at"].nullable is False


def test_file_backup_enums_are_stable_lowercase_values():
    expected = {
        FileBackupStrategy: {"full", "incremental", "differential"},
        FileBackupFormat: {"direct", "zip64"},
        FileBackupFilterKind: {"include", "exclude"},
        FileBackupFilterOperator: {"glob", "extension", "relative_path"},
        FileBackupRunStatus: {
            "queued",
            "preflight",
            "running",
            "completed",
            "completed_with_warnings",
            "retryable",
            "failed",
            "cancelled",
        },
    }

    for enum_type, values in expected.items():
        assert issubclass(enum_type, enum.Enum)
        assert {item.value for item in enum_type} == values


def test_task_references_agent_destination_and_revisioned_configuration():
    columns = FileBackupTask.__table__.columns

    for name in (
        "name",
        "agent_id",
        "destination_profile_id",
        "strategy",
        "format",
        "schedule",
        "timezone_name",
        "missed_run_policy",
        "retention_full_chains",
        "vss_policy",
        "verification_mode",
        "config_revision",
        "is_active",
        "updated_at",
    ):
        assert name in columns

    assert columns["agent_id"].nullable is False
    assert columns["destination_profile_id"].nullable is False
    assert columns["config_revision"].nullable is False
    assert ("tenant_id", "id") in _unique_column_sets(FileBackupTask)


def test_sources_and_filters_cannot_cross_task_tenants():
    assert (("tenant_id", "task_id"), "file_backup_tasks") in _composite_foreign_keys(
        FileBackupSource
    )
    assert (("tenant_id", "task_id"), "file_backup_tasks") in _composite_foreign_keys(
        FileBackupFilter
    )
    assert ("tenant_id", "task_id", "path") in _unique_column_sets(FileBackupSource)
    assert (
        "tenant_id",
        "task_id",
        "kind",
        "operator",
        "pattern",
    ) in _unique_column_sets(FileBackupFilter)


def test_runs_keep_progress_checkpoint_and_sanitized_error_state():
    columns = FileBackupRun.__table__.columns

    for name in (
        "task_id",
        "agent_id",
        "chain_id",
        "parent_run_id",
        "config_revision",
        "strategy",
        "status",
        "phase",
        "progress_percent",
        "files_total",
        "files_processed",
        "bytes_total",
        "bytes_processed",
        "checkpoint_ref",
        "summary",
        "error_code",
        "error_message",
        "started_at",
        "finished_at",
        "updated_at",
    ):
        assert name in columns

    assert (("tenant_id", "task_id"), "file_backup_tasks") in _composite_foreign_keys(
        FileBackupRun
    )
    assert (("tenant_id", "chain_id"), "file_backup_chains") in _composite_foreign_keys(
        FileBackupRun
    )


def test_chains_and_artifacts_preserve_history_and_protection_state():
    chain_columns = FileBackupChain.__table__.columns
    artifact_columns = FileBackupArtifact.__table__.columns

    for name in ("task_id", "status", "full_started_at", "latest_run_at"):
        assert name in chain_columns
    for name in (
        "run_id",
        "chain_id",
        "kind",
        "location",
        "size_bytes",
        "sha256",
        "manifest_ref",
        "manifest_summary",
        "protected",
        "protected_at",
        "protected_by",
    ):
        assert name in artifact_columns

    assert artifact_columns["protected"].nullable is False
    assert (("tenant_id", "run_id"), "file_backup_runs") in _composite_foreign_keys(
        FileBackupArtifact
    )
    assert (("tenant_id", "chain_id"), "file_backup_chains") in _composite_foreign_keys(
        FileBackupArtifact
    )


def test_restore_jobs_require_immutable_simulation_confirmations():
    job_columns = FileRestoreJob.__table__.columns
    confirmation_columns = FileRestoreConfirmation.__table__.columns

    for name in (
        "chain_id",
        "agent_id",
        "status",
        "destination_mode",
        "destination_path",
        "selection_summary",
        "simulation_summary",
        "simulation_hash",
        "error_code",
        "error_message",
        "started_at",
        "finished_at",
    ):
        assert name in job_columns
    for name in (
        "restore_job_id",
        "simulation_hash",
        "created_by",
        "expires_at",
        "consumed_at",
    ):
        assert name in confirmation_columns

    assert (
        ("tenant_id", "restore_job_id"),
        "file_restore_jobs",
    ) in _composite_foreign_keys(FileRestoreConfirmation)


def test_postgres_metadata_does_not_include_per_file_catalog_table():
    forbidden = {"file_backup_files", "file_catalog_entries", "file_catalog_files"}
    assert forbidden.isdisjoint(Base.metadata.tables)
