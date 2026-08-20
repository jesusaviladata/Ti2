"""Add agent-backed automatic backup plans.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "agent_backup_plans",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("tenant_id", uuid_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("agent_id", uuid_type, nullable=False),
        sa.Column("sql_profile_id", sa.String(64), nullable=False),
        sa.Column("destination_profile_id", sa.String(64)),
        sa.Column(
            "database_names",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("local_time", sa.String(5), server_default="02:00", nullable=False),
        sa.Column(
            "timezone_name",
            sa.String(64),
            server_default="America/Mexico_City",
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["remote_agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_agent_backup_plan_name"),
    )
    op.create_index("ix_agent_backup_plans_tenant_id", "agent_backup_plans", ["tenant_id"])
    op.create_index("ix_agent_backup_plans_agent_id", "agent_backup_plans", ["agent_id"])
    op.create_index(
        "ix_agent_backup_plans_active",
        "agent_backup_plans",
        ["tenant_id", "is_active", "next_run_at"],
    )


def downgrade() -> None:
    op.drop_table("agent_backup_plans")
