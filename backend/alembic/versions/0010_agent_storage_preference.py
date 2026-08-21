"""Add tenant storage display preference.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_storage_thresholds",
        sa.Column("preferred_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agent_storage_thresholds",
        sa.Column("preferred_volume_key", sa.String(length=128), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_storage_thresholds_preferred_agent",
        "agent_storage_thresholds",
        "remote_agents",
        ["preferred_agent_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_agent_storage_thresholds_preferred_agent",
        "agent_storage_thresholds",
        type_="foreignkey",
    )
    op.drop_column("agent_storage_thresholds", "preferred_volume_key")
    op.drop_column("agent_storage_thresholds", "preferred_agent_id")
