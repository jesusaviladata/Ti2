"""Add durable Windows agents and agent-backed remote servers.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004"
down_revision: Union[str, None] = "0003"
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
    op.create_table(
        "remote_agents",
        *_identity_columns(),
        sa.Column("installation_id", sa.String(128), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("os_version", sa.String(255), server_default="", nullable=False),
        sa.Column("agent_version", sa.String(50), nullable=False),
        sa.Column("public_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(30), server_default="pending", nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by_id", UUID),
        sa.Column(
            "metadata_json",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        _tenant_fk(),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"], ["remote_agents.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "installation_id", name="uq_remote_agent_installation"
        ),
    )
    op.create_index("ix_remote_agents_tenant_id", "remote_agents", ["tenant_id"])
    op.create_index(
        "ix_remote_agents_status_seen",
        "remote_agents",
        ["tenant_id", "status", "last_seen_at"],
    )

    op.create_table(
        "agent_pairing_tokens",
        *_identity_columns(),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID),
        sa.Column("replace_agent_id", UUID),
        _tenant_fk(),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["replace_agent_id"], ["remote_agents.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_agent_pairing_token_hash"),
    )
    op.create_index(
        "ix_agent_pairing_tokens_tenant_id",
        "agent_pairing_tokens",
        ["tenant_id"],
    )
    op.create_index(
        "ix_agent_pairing_expiry",
        "agent_pairing_tokens",
        ["expires_at", "used_at"],
    )

    op.create_table(
        "agent_request_nonces",
        *_identity_columns(),
        sa.Column("agent_id", UUID, nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _tenant_fk(),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["remote_agents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_id", "nonce_hash", name="uq_agent_request_nonce"
        ),
    )
    op.create_index(
        "ix_agent_request_nonces_tenant_id",
        "agent_request_nonces",
        ["tenant_id"],
    )
    op.create_index(
        "ix_agent_request_nonces_expiry",
        "agent_request_nonces",
        ["expires_at"],
    )

    op.add_column(
        "remote_servers",
        sa.Column(
            "transport", sa.String(10), server_default="legacy", nullable=False
        ),
    )
    op.add_column("remote_servers", sa.Column("agent_id", UUID))
    op.add_column(
        "remote_servers",
        sa.Column(
            "target_folders",
            JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "remote_servers",
        sa.Column(
            "target_files",
            JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "remote_servers",
        sa.Column("config_revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "remote_servers", sa.Column("configuration_hash", sa.String(64))
    )
    op.add_column(
        "remote_servers", sa.Column("validated_at", sa.DateTime(timezone=True))
    )
    op.create_foreign_key(
        "fk_remote_servers_agent_id",
        "remote_servers",
        "remote_agents",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_remote_servers_agent_id", "remote_servers", ["agent_id"])
    for column in ("protocol", "host", "port", "username"):
        op.alter_column("remote_servers", column, existing_nullable=False, nullable=True)

    op.create_table(
        "agent_commands",
        *_identity_columns(),
        sa.Column("agent_id", UUID, nullable=False),
        sa.Column("job_id", UUID),
        sa.Column("command_type", sa.String(80), nullable=False),
        sa.Column(
            "payload",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), server_default="pending", nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "result_summary",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        _tenant_fk(),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["remote_agents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["background_jobs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_id", "idempotency_key", name="uq_agent_command_idempotency"
        ),
    )
    op.create_index("ix_agent_commands_tenant_id", "agent_commands", ["tenant_id"])
    op.create_index(
        "ix_agent_commands_pending",
        "agent_commands",
        ["agent_id", "status", "expires_at", "created_at"],
    )

    op.create_table(
        "remote_structure_validations",
        *_identity_columns(),
        sa.Column("server_id", UUID, nullable=False),
        sa.Column("agent_id", UUID, nullable=False),
        sa.Column("job_id", UUID),
        sa.Column("configuration_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column(
            "summary",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("validated_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _tenant_fk(),
        sa.ForeignKeyConstraint(
            ["server_id"], ["remote_servers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["remote_agents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["background_jobs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_remote_structure_validations_tenant_id",
        "remote_structure_validations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_remote_structure_validation_server",
        "remote_structure_validations",
        ["tenant_id", "server_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_agent_servers = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM remote_servers WHERE transport = 'agent')")
    ).scalar()
    if has_agent_servers:
        raise RuntimeError(
            "No se puede revertir 0004 mientras existan servidores de agente; "
            "expórtelos o elimínelos mediante el flujo administrativo primero."
        )

    op.drop_table("remote_structure_validations")
    op.drop_table("agent_commands")
    for column in ("protocol", "host", "port", "username"):
        op.alter_column("remote_servers", column, existing_nullable=True, nullable=False)
    op.drop_index("ix_remote_servers_agent_id", table_name="remote_servers")
    op.drop_constraint(
        "fk_remote_servers_agent_id", "remote_servers", type_="foreignkey"
    )
    for column in (
        "validated_at",
        "configuration_hash",
        "config_revision",
        "target_files",
        "target_folders",
        "agent_id",
        "transport",
    ):
        op.drop_column("remote_servers", column)
    op.drop_table("agent_request_nonces")
    op.drop_table("agent_pairing_tokens")
    op.drop_table("remote_agents")

