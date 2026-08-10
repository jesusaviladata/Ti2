"""Persist operational modules used by the production API.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _identity_columns() -> list[sa.Column]:
    return [
        sa.Column("id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _tenant_fk() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
    )


def upgrade() -> None:
    op.execute("ALTER TYPE backuptype ADD VALUE IF NOT EXISTS 'log'")
    op.add_column(
        "access_logs", sa.Column("client_name", sa.String(255), nullable=True)
    )
    op.add_column(
        "access_logs", sa.Column("notes", sa.String(2048), nullable=True)
    )
    op.add_column(
        "access_logs",
        sa.Column(
            "status",
            sa.String(20),
            server_default="active",
            nullable=False,
        ),
    )

    op.create_table(
        "backup_schedules",
        sa.Column("id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("database_name", sa.String(255), nullable=False),
        sa.Column("backup_type", sa.String(20), nullable=False),
        sa.Column("destination", sa.String(50), nullable=False),
        sa.Column("cron_expression", sa.String(100), nullable=False),
        sa.Column(
            "retention_count", sa.Integer(), server_default="10", nullable=False
        ),
        sa.Column(
            "retention_days", sa.Integer(), server_default="30", nullable=False
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default="true", nullable=False
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backup_schedules_tenant_id", "backup_schedules", ["tenant_id"]
    )

    op.create_table(
        "cleanup_folders",
        *_identity_columns(),
        sa.Column("path", sa.String(2048), nullable=False),
        sa.Column("label", sa.String(255), server_default="", nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default="true", nullable=False
        ),
        _tenant_fk(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "path", name="uq_cleanup_folder_tenant_path"
        ),
    )
    op.create_index(
        "ix_cleanup_folders_tenant_id", "cleanup_folders", ["tenant_id"]
    )

    op.create_table(
        "cleanup_rules",
        *_identity_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("folder_id", UUID),
        sa.Column(
            "patterns",
            JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "extensions",
            JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "keep_policy",
            sa.String(20),
            server_default="latest",
            nullable=False,
        ),
        sa.Column("keep_n", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "min_age_days", sa.Float(), server_default="0", nullable=False
        ),
        sa.Column(
            "enabled", sa.Boolean(), server_default="true", nullable=False
        ),
        _tenant_fk(),
        sa.ForeignKeyConstraint(
            ["folder_id"], ["cleanup_folders.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "name", name="uq_cleanup_rule_tenant_name"
        ),
    )
    op.create_index(
        "ix_cleanup_rules_tenant_id", "cleanup_rules", ["tenant_id"]
    )
    op.create_index(
        "ix_cleanup_rules_folder_id", "cleanup_rules", ["folder_id"]
    )

    op.create_table(
        "cleanup_schedules",
        *_identity_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("folder_id", UUID, nullable=False),
        sa.Column("rule_id", UUID, nullable=False),
        sa.Column("cron_expression", sa.String(100), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default="true", nullable=False
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        _tenant_fk(),
        sa.ForeignKeyConstraint(
            ["folder_id"], ["cleanup_folders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["cleanup_rules.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "name", name="uq_cleanup_schedule_tenant_name"
        ),
    )
    op.create_index(
        "ix_cleanup_schedules_tenant_id", "cleanup_schedules", ["tenant_id"]
    )
    op.create_index(
        "ix_cleanup_schedules_next_run",
        "cleanup_schedules",
        ["tenant_id", "enabled", "next_run_at"],
    )

    op.create_table(
        "cleanup_simulations",
        *_identity_columns(),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("folder_id", UUID),
        sa.Column("rule_id", UUID),
        sa.Column(
            "snapshot",
            JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        _tenant_fk(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["folder_id"], ["cleanup_folders.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["cleanup_rules.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cleanup_simulations_tenant_id",
        "cleanup_simulations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_cleanup_simulations_expiry",
        "cleanup_simulations",
        ["tenant_id", "expires_at"],
    )

    op.create_table(
        "cleanup_executions",
        *_identity_columns(),
        sa.Column("user_id", UUID),
        sa.Column(
            "kind", sa.String(40), server_default="local", nullable=False
        ),
        sa.Column(
            "status", sa.String(30), server_default="running", nullable=False
        ),
        sa.Column(
            "files_deleted", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "bytes_freed", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column(
            "errors_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "details",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        _tenant_fk(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cleanup_executions_tenant_id",
        "cleanup_executions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_cleanup_executions_tenant_started",
        "cleanup_executions",
        ["tenant_id", "started_at"],
    )

    op.create_table(
        "cleanup_trash_items",
        *_identity_columns(),
        sa.Column("execution_id", UUID),
        sa.Column("rule_id", UUID),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("original_path", sa.String(2048), nullable=False),
        sa.Column("trash_path", sa.String(2048), nullable=False),
        sa.Column(
            "size_bytes", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("deleted_by", UUID),
        sa.Column("restored_at", sa.DateTime(timezone=True)),
        sa.Column("purged_at", sa.DateTime(timezone=True)),
        _tenant_fk(),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["cleanup_executions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["cleanup_rules.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cleanup_trash_items_tenant_id",
        "cleanup_trash_items",
        ["tenant_id"],
    )
    op.create_index(
        "ix_cleanup_trash_tenant_created",
        "cleanup_trash_items",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "remote_servers",
        *_identity_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("protocol", sa.String(10), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("base_path", sa.String(2048), nullable=False),
        sa.Column(
            "allowlist",
            JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        _tenant_fk(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "name", name="uq_remote_server_tenant_name"
        ),
    )
    op.create_index(
        "ix_remote_servers_tenant_id", "remote_servers", ["tenant_id"]
    )

    op.create_table(
        "ssh_host_keys",
        *_identity_columns(),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("algorithm", sa.String(100), nullable=False),
        sa.Column("fingerprint", sa.String(255), nullable=False),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        _tenant_fk(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "host",
            "port",
            name="uq_ssh_host_key_tenant_host_port",
        ),
    )
    op.create_index(
        "ix_ssh_host_keys_tenant_id", "ssh_host_keys", ["tenant_id"]
    )

    op.create_table(
        "remote_cleanup_executions",
        *_identity_columns(),
        sa.Column("server_id", UUID, nullable=False),
        sa.Column("user_id", UUID),
        sa.Column(
            "kind", sa.String(40), server_default="manual", nullable=False
        ),
        sa.Column(
            "status", sa.String(30), server_default="running", nullable=False
        ),
        sa.Column(
            "targets",
            JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "summary",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        _tenant_fk(),
        sa.ForeignKeyConstraint(
            ["server_id"], ["remote_servers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_remote_cleanup_executions_tenant_id",
        "remote_cleanup_executions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_remote_cleanup_tenant_started",
        "remote_cleanup_executions",
        ["tenant_id", "started_at"],
    )

    op.create_table(
        "remote_quarantine_items",
        *_identity_columns(),
        sa.Column("execution_id", UUID),
        sa.Column("server_id", UUID, nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("original_path", sa.String(2048), nullable=False),
        sa.Column("quarantine_path", sa.String(2048), nullable=False),
        sa.Column(
            "size_bytes", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("moved_by", UUID),
        sa.Column(
            "retention_days", sa.Integer(), server_default="15", nullable=False
        ),
        sa.Column("restored_at", sa.DateTime(timezone=True)),
        sa.Column("purged_at", sa.DateTime(timezone=True)),
        _tenant_fk(),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["remote_cleanup_executions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["server_id"], ["remote_servers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["moved_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_remote_quarantine_items_tenant_id",
        "remote_quarantine_items",
        ["tenant_id"],
    )
    op.create_index(
        "ix_remote_quarantine_tenant_created",
        "remote_quarantine_items",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "background_jobs",
        *_identity_columns(),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column(
            "status", sa.String(30), server_default="running", nullable=False
        ),
        sa.Column(
            "phase", sa.String(100), server_default="queued", nullable=False
        ),
        sa.Column("resource_id", UUID),
        sa.Column(
            "total_units", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "processed_units", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "found_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("result", JSONB),
        sa.Column("error", sa.Text()),
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        _tenant_fk(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_background_jobs_tenant_id", "background_jobs", ["tenant_id"]
    )
    op.create_index(
        "ix_background_jobs_tenant_status",
        "background_jobs",
        ["tenant_id", "status"],
    )

    op.create_table(
        "notifications",
        *_identity_columns(),
        sa.Column("user_id", UUID),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "severity", sa.String(20), server_default="info", nullable=False
        ),
        sa.Column(
            "is_read", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "metadata_json",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        _tenant_fk(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_tenant_id", "notifications", ["tenant_id"]
    )
    op.create_index(
        "ix_notifications_tenant_created",
        "notifications",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    for table in (
        "notifications",
        "background_jobs",
        "remote_quarantine_items",
        "remote_cleanup_executions",
        "ssh_host_keys",
        "remote_servers",
        "cleanup_trash_items",
        "cleanup_executions",
        "cleanup_simulations",
        "cleanup_schedules",
        "cleanup_rules",
        "cleanup_folders",
        "backup_schedules",
    ):
        op.drop_table(table)
    op.drop_column("access_logs", "status")
    op.drop_column("access_logs", "notes")
    op.drop_column("access_logs", "client_name")
