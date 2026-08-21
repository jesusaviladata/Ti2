"""Add managed file backup administrative state.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
    )


def upgrade() -> None:
    op.create_table(
        "file_backup_tasks",
        *_tenant_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "destination_profile_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "strategy",
            _enum(
                "file_backup_strategy", "full", "incremental", "differential"
            ),
            nullable=False,
        ),
        sa.Column(
            "format",
            _enum("file_backup_format", "direct", "zip64"),
            nullable=False,
        ),
        sa.Column(
            "schedule",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "timezone_name",
            sa.String(64),
            server_default="America/Mexico_City",
            nullable=False,
        ),
        sa.Column(
            "missed_run_policy", sa.String(30), server_default="run_once", nullable=False
        ),
        sa.Column(
            "retention_full_chains", sa.Integer(), server_default="4", nullable=False
        ),
        sa.Column(
            "vss_policy", sa.String(20), server_default="preferred", nullable=False
        ),
        sa.Column(
            "verification_mode", sa.String(20), server_default="sha256", nullable=False
        ),
        sa.Column("config_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "retention_full_chains >= 1", name="ck_file_backup_task_retention"
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["remote_agents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["destination_profile_id"],
            ["agent_connection_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_file_backup_task_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "agent_id", "name", name="uq_file_backup_task_agent_name"
        ),
    )
    op.create_index(
        "ix_file_backup_tasks_tenant_id", "file_backup_tasks", ["tenant_id"]
    )
    op.create_index(
        "ix_file_backup_tasks_tenant_active",
        "file_backup_tasks",
        ["tenant_id", "is_active"],
    )
    op.create_index(
        "ix_file_backup_tasks_tenant_agent",
        "file_backup_tasks",
        ["tenant_id", "agent_id"],
    )

    op.create_table(
        "file_backup_sources",
        *_tenant_columns(),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.String(2048), nullable=False),
        sa.Column(
            "include_subfolders", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["file_backup_tasks.tenant_id", "file_backup_tasks.id"],
            ondelete="CASCADE",
            name="fk_file_backup_source_tenant_task",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "task_id", "path", name="uq_file_backup_source_task_path"
        ),
    )
    op.create_index(
        "ix_file_backup_sources_tenant_id", "file_backup_sources", ["tenant_id"]
    )
    op.create_index(
        "ix_file_backup_sources_tenant_task",
        "file_backup_sources",
        ["tenant_id", "task_id"],
    )

    op.create_table(
        "file_backup_filters",
        *_tenant_columns(),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "kind",
            _enum("file_backup_filter_kind", "include", "exclude"),
            nullable=False,
        ),
        sa.Column(
            "operator",
            _enum(
                "file_backup_filter_operator",
                "glob",
                "extension",
                "relative_path",
            ),
            nullable=False,
        ),
        sa.Column("pattern", sa.String(1024), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["file_backup_tasks.tenant_id", "file_backup_tasks.id"],
            ondelete="CASCADE",
            name="fk_file_backup_filter_tenant_task",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "task_id",
            "kind",
            "operator",
            "pattern",
            name="uq_file_backup_filter_task_rule",
        ),
    )
    op.create_index(
        "ix_file_backup_filters_tenant_id", "file_backup_filters", ["tenant_id"]
    )
    op.create_index(
        "ix_file_backup_filters_tenant_task",
        "file_backup_filters",
        ["tenant_id", "task_id"],
    )

    op.create_table(
        "file_backup_chains",
        *_tenant_columns(),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(30), server_default="open", nullable=False),
        sa.Column("full_started_at", sa.DateTime(timezone=True)),
        sa.Column("latest_run_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["file_backup_tasks.tenant_id", "file_backup_tasks.id"],
            ondelete="RESTRICT",
            name="fk_file_backup_chain_tenant_task",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_file_backup_chain_tenant_id"),
    )
    op.create_index(
        "ix_file_backup_chains_tenant_id", "file_backup_chains", ["tenant_id"]
    )
    op.create_index(
        "ix_file_backup_chains_tenant_task",
        "file_backup_chains",
        ["tenant_id", "task_id"],
    )
    op.create_index(
        "ix_file_backup_chains_tenant_status",
        "file_backup_chains",
        ["tenant_id", "status"],
    )

    op.create_table(
        "file_backup_runs",
        *_tenant_columns(),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chain_id", postgresql.UUID(as_uuid=True)),
        sa.Column("parent_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("config_revision", sa.Integer(), nullable=False),
        sa.Column(
            "strategy",
            _enum(
                "file_backup_run_strategy", "full", "incremental", "differential"
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum(
                "file_backup_run_status",
                "queued",
                "preflight",
                "running",
                "completed",
                "completed_with_warnings",
                "retryable",
                "failed",
                "cancelled",
            ),
            nullable=False,
        ),
        sa.Column("phase", sa.String(40), server_default="queued", nullable=False),
        sa.Column("progress_percent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("files_total", sa.BigInteger()),
        sa.Column("files_processed", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("bytes_total", sa.BigInteger()),
        sa.Column("bytes_processed", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("checkpoint_ref", sa.String(1024)),
        sa.Column(
            "summary",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_file_backup_run_progress",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["file_backup_tasks.tenant_id", "file_backup_tasks.id"],
            ondelete="RESTRICT",
            name="fk_file_backup_run_tenant_task",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "chain_id"],
            ["file_backup_chains.tenant_id", "file_backup_chains.id"],
            ondelete="RESTRICT",
            name="fk_file_backup_run_tenant_chain",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_run_id"],
            ["file_backup_runs.tenant_id", "file_backup_runs.id"],
            ondelete="RESTRICT",
            name="fk_file_backup_run_tenant_parent",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["remote_agents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_file_backup_run_tenant_id"),
    )
    op.create_index(
        "ix_file_backup_runs_tenant_id", "file_backup_runs", ["tenant_id"]
    )
    op.create_index(
        "ix_file_backup_runs_tenant_status_created",
        "file_backup_runs",
        ["tenant_id", "status", "created_at"],
    )
    op.create_index(
        "ix_file_backup_runs_tenant_task_created",
        "file_backup_runs",
        ["tenant_id", "task_id", "created_at"],
    )

    op.create_table(
        "file_backup_artifacts",
        *_tenant_columns(),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chain_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("location", sa.String(2048), nullable=False),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("sha256", sa.String(64)),
        sa.Column("manifest_ref", sa.String(2048)),
        sa.Column(
            "manifest_summary",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("protected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("protected_at", sa.DateTime(timezone=True)),
        sa.Column("protected_by", postgresql.UUID(as_uuid=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["file_backup_runs.tenant_id", "file_backup_runs.id"],
            ondelete="RESTRICT",
            name="fk_file_backup_artifact_tenant_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "chain_id"],
            ["file_backup_chains.tenant_id", "file_backup_chains.id"],
            ondelete="RESTRICT",
            name="fk_file_backup_artifact_tenant_chain",
        ),
        sa.ForeignKeyConstraint(["protected_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "run_id", "location", name="uq_file_backup_artifact_run_location"
        ),
    )
    op.create_index(
        "ix_file_backup_artifacts_tenant_id", "file_backup_artifacts", ["tenant_id"]
    )
    op.create_index(
        "ix_file_backup_artifacts_tenant_created",
        "file_backup_artifacts",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_file_backup_artifacts_tenant_protected",
        "file_backup_artifacts",
        ["tenant_id", "protected"],
    )

    op.create_table(
        "file_restore_jobs",
        *_tenant_columns(),
        sa.Column("chain_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            _enum(
                "file_restore_status",
                "queued",
                "simulating",
                "awaiting_confirmation",
                "restoring",
                "completed",
                "completed_with_warnings",
                "failed",
                "cancelled",
            ),
            nullable=False,
        ),
        sa.Column("destination_mode", sa.String(20), nullable=False),
        sa.Column("destination_path", sa.String(2048), nullable=False),
        sa.Column(
            "selection_summary",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "simulation_summary",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("simulation_hash", sa.String(64)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "chain_id"],
            ["file_backup_chains.tenant_id", "file_backup_chains.id"],
            ondelete="RESTRICT",
            name="fk_file_restore_job_tenant_chain",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["remote_agents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_file_restore_job_tenant_id"),
    )
    op.create_index(
        "ix_file_restore_jobs_tenant_id", "file_restore_jobs", ["tenant_id"]
    )
    op.create_index(
        "ix_file_restore_jobs_tenant_status_created",
        "file_restore_jobs",
        ["tenant_id", "status", "created_at"],
    )

    op.create_table(
        "file_restore_confirmations",
        *_tenant_columns(),
        sa.Column("restore_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("simulation_hash", sa.String(64), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "restore_job_id"],
            ["file_restore_jobs.tenant_id", "file_restore_jobs.id"],
            ondelete="RESTRICT",
            name="fk_file_restore_confirmation_tenant_job",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "restore_job_id", name="uq_file_restore_confirmation_job"
        ),
    )
    op.create_index(
        "ix_file_restore_confirmations_tenant_id",
        "file_restore_confirmations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_file_restore_confirmations_tenant_expiry",
        "file_restore_confirmations",
        ["tenant_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_table("file_restore_confirmations")
    op.drop_table("file_restore_jobs")
    op.drop_table("file_backup_artifacts")
    op.drop_table("file_backup_runs")
    op.drop_table("file_backup_chains")
    op.drop_table("file_backup_filters")
    op.drop_table("file_backup_sources")
    op.drop_table("file_backup_tasks")
