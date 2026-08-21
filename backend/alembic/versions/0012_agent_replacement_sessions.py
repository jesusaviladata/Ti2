"""Add confirmed two-phase agent replacement sessions.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "remote_agents",
        sa.Column("lineage_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute("UPDATE remote_agents SET lineage_id = id WHERE lineage_id IS NULL")
    op.create_index(
        "ix_remote_agents_lineage_id", "remote_agents", ["lineage_id"]
    )

    op.create_table(
        "agent_replacement_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("old_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_agent_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "status",
            sa.String(30),
            server_default="awaiting_candidate",
            nullable=False,
        ),
        sa.Column(
            "expected_old_revision", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column(
            "audit_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["old_agent_id"], ["remote_agents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_agent_id"], ["remote_agents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "candidate_agent_id",
            name="uq_agent_replacement_candidate",
        ),
    )
    op.create_index(
        "ix_agent_replacement_sessions_tenant_id",
        "agent_replacement_sessions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_agent_replacement_tenant_status_expiry",
        "agent_replacement_sessions",
        ["tenant_id", "status", "expires_at"],
    )

    op.add_column(
        "agent_pairing_tokens",
        sa.Column(
            "replacement_session_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_agent_pairing_replacement_session",
        "agent_pairing_tokens",
        "agent_replacement_sessions",
        ["replacement_session_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_agent_pairing_replacement_session",
        "agent_pairing_tokens",
        type_="foreignkey",
    )
    op.drop_column("agent_pairing_tokens", "replacement_session_id")
    op.drop_table("agent_replacement_sessions")
    op.drop_index("ix_remote_agents_lineage_id", table_name="remote_agents")
    op.drop_column("remote_agents", "lineage_id")
