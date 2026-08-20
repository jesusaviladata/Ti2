"""Add tenant-configurable agent storage thresholds.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_storage_thresholds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "warning_free_percent", sa.Float(), server_default="20", nullable=False
        ),
        sa.Column(
            "warning_free_bytes",
            sa.BigInteger(),
            server_default=str(20 * 1024**3),
            nullable=False,
        ),
        sa.Column(
            "critical_free_percent", sa.Float(), server_default="10", nullable=False
        ),
        sa.Column(
            "critical_free_bytes",
            sa.BigInteger(),
            server_default=str(10 * 1024**3),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_agent_storage_threshold_tenant"),
    )
    op.create_index(
        "ix_agent_storage_thresholds_tenant_id",
        "agent_storage_thresholds",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_table("agent_storage_thresholds")
