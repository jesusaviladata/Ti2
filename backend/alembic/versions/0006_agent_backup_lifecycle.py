"""Add agent backup and delivery lifecycle fields.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("backups", sa.Column("agent_id", postgresql.UUID(as_uuid=True)))
    op.add_column("backups", sa.Column("run_id", sa.String(64)))
    op.add_column("backups", sa.Column("phase", sa.String(100)))
    op.add_column(
        "backups",
        sa.Column("progress_percent", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("backups", sa.Column("validation_method", sa.String(50)))
    op.add_column("backups", sa.Column("trigger_reason", sa.String(100)))
    op.add_column(
        "backups",
        sa.Column("delivery_status", sa.String(30), server_default="pending", nullable=False),
    )
    op.add_column("backups", sa.Column("delivery_phase", sa.String(100)))
    op.add_column(
        "backups",
        sa.Column("delivery_progress", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("backups", sa.Column("delivery_error_message", sa.Text()))
    op.add_column("backups", sa.Column("delivery_profile_id", sa.String(128)))
    op.add_column("backups", sa.Column("archive_path", sa.String(2048)))
    op.add_column("backups", sa.Column("archive_size_bytes", sa.BigInteger()))
    op.add_column("backups", sa.Column("archive_sha256", sa.String(64)))
    op.create_foreign_key(
        "fk_backups_agent_id_remote_agents",
        "backups",
        "remote_agents",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_backups_run_id", "backups", ["run_id"])
    op.create_index("ix_backups_agent_id", "backups", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_backups_agent_id", table_name="backups")
    op.drop_index("ix_backups_run_id", table_name="backups")
    op.drop_constraint("fk_backups_agent_id_remote_agents", "backups", type_="foreignkey")
    for name in (
        "archive_sha256",
        "archive_size_bytes",
        "archive_path",
        "delivery_error_message",
        "delivery_profile_id",
        "delivery_progress",
        "delivery_phase",
        "delivery_status",
        "validation_method",
        "trigger_reason",
        "progress_percent",
        "phase",
        "run_id",
        "agent_id",
    ):
        op.drop_column("backups", name)
