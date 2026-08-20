"""agent weekly backup plans

Revision ID: 0006_agent_backup_plans
Revises: 0005_agent_backup_lifecycle
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_backup_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("remote_agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sql_profile_id", sa.String(128), nullable=False),
        sa.Column("destination_profile_id", sa.String(128)),
        sa.Column("database_names", postgresql.JSONB(), nullable=False),
        sa.Column("full_days", postgresql.JSONB(), nullable=False),
        sa.Column("differential_days", postgresql.JSONB(), nullable=False),
        sa.Column("hour_utc", sa.Integer(), server_default="8", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_backup_plans_tenant_id", "agent_backup_plans", ["tenant_id"])
    op.create_index("ix_agent_backup_plans_agent_id", "agent_backup_plans", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_backup_plans_agent_id", table_name="agent_backup_plans")
    op.drop_index("ix_agent_backup_plans_tenant_id", table_name="agent_backup_plans")
    op.drop_table("agent_backup_plans")
