"""Add agent storage health, managed profiles, and backup origin.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0008"
down_revision: Union[str, None] = "0007"
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


def upgrade() -> None:
    op.add_column(
        "backups", sa.Column("origin_snapshot", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "remote_agents", sa.Column("encryption_public_key", sa.String(128))
    )
    op.add_column(
        "remote_agents", sa.Column("last_heartbeat_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "remote_agents",
        sa.Column(
            "desired_config_revision",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "remote_agents",
        sa.Column(
            "applied_config_revision",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "remote_agents",
        sa.Column(
            "health_status",
            sa.String(30),
            server_default="unknown",
            nullable=False,
        ),
    )

    op.create_table(
        "agent_volume_states",
        *_tenant_columns(),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("volume_key", sa.String(128), nullable=False),
        sa.Column("label", sa.String(255), server_default="", nullable=False),
        sa.Column("mount_point", sa.String(512), nullable=False),
        sa.Column("total_bytes", sa.BigInteger()),
        sa.Column("free_bytes", sa.BigInteger()),
        sa.Column("used_percent", sa.Float()),
        sa.Column(
            "roles",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.String(512)),
        sa.ForeignKeyConstraint(["agent_id"], ["remote_agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "agent_id",
            "volume_key",
            name="uq_agent_volume_state_agent_volume",
        ),
    )
    op.create_index("ix_agent_volume_states_tenant_id", "agent_volume_states", ["tenant_id"])
    op.create_index("ix_agent_volume_states_agent_id", "agent_volume_states", ["agent_id"])
    op.create_index(
        "ix_agent_volume_states_tenant_agent_observed",
        "agent_volume_states",
        ["tenant_id", "agent_id", "observed_at"],
    )

    op.create_table(
        "agent_storage_alerts",
        *_tenant_columns(),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("volume_key", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="open", nullable=False),
        sa.Column("free_bytes", sa.BigInteger()),
        sa.Column("total_bytes", sa.BigInteger()),
        sa.Column("free_percent", sa.Float()),
        sa.Column(
            "thresholds",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["agent_id"], ["remote_agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_storage_alerts_tenant_id", "agent_storage_alerts", ["tenant_id"])
    op.create_index("ix_agent_storage_alerts_agent_id", "agent_storage_alerts", ["agent_id"])
    op.create_index(
        "ix_agent_storage_alerts_tenant_status",
        "agent_storage_alerts",
        ["tenant_id", "status", "last_observed_at"],
    )
    op.create_index(
        "uq_agent_storage_alert_open",
        "agent_storage_alerts",
        ["tenant_id", "agent_id", "volume_key"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "agent_connection_profiles",
        *_tenant_columns(),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_type", sa.String(20), nullable=False),
        sa.Column("profile_key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column(
            "public_config",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("secret_envelope", sa.Text()),
        sa.Column("desired_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("applied_revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sync_status", sa.String(30), server_default="pending", nullable=False),
        sa.Column("last_test_status", sa.String(30)),
        sa.Column("last_test_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["remote_agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "agent_id",
            "profile_type",
            "profile_key",
            name="uq_agent_connection_profile_key",
        ),
    )
    op.create_index(
        "ix_agent_connection_profiles_tenant_id", "agent_connection_profiles", ["tenant_id"]
    )
    op.create_index(
        "ix_agent_connection_profiles_agent_id", "agent_connection_profiles", ["agent_id"]
    )
    op.create_index(
        "ix_agent_connection_profiles_tenant_active",
        "agent_connection_profiles",
        ["tenant_id", "agent_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_table("agent_connection_profiles")
    op.drop_table("agent_storage_alerts")
    op.drop_table("agent_volume_states")
    op.drop_column("remote_agents", "health_status")
    op.drop_column("remote_agents", "applied_config_revision")
    op.drop_column("remote_agents", "desired_config_revision")
    op.drop_column("remote_agents", "last_heartbeat_at")
    op.drop_column("remote_agents", "encryption_public_key")
    op.drop_column("backups", "origin_snapshot")
