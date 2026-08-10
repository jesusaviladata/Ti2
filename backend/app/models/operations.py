from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TenantRecord:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class CleanupFolder(TenantRecord, Base):
    __tablename__ = "cleanup_folders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "path", name="uq_cleanup_folder_tenant_path"),
    )

    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CleanupRule(TenantRecord, Base):
    __tablename__ = "cleanup_rules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_cleanup_rule_tenant_name"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cleanup_folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    patterns: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    extensions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    keep_policy: Mapped[str] = mapped_column(String(20), nullable=False, default="latest")
    keep_n: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    min_age_days: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CleanupSchedule(TenantRecord, Base):
    __tablename__ = "cleanup_schedules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_cleanup_schedule_tenant_name"),
        Index("ix_cleanup_schedules_next_run", "tenant_id", "enabled", "next_run_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    folder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cleanup_folders.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cleanup_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CleanupSimulation(TenantRecord, Base):
    __tablename__ = "cleanup_simulations"
    __table_args__ = (
        Index("ix_cleanup_simulations_expiry", "tenant_id", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cleanup_folders.id", ondelete="SET NULL")
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cleanup_rules.id", ondelete="SET NULL")
    )
    snapshot: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CleanupExecution(TenantRecord, Base):
    __tablename__ = "cleanup_executions"
    __table_args__ = (
        Index("ix_cleanup_executions_tenant_started", "tenant_id", "started_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="local")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running")
    files_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bytes_freed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CleanupTrashItem(TenantRecord, Base):
    __tablename__ = "cleanup_trash_items"
    __table_args__ = (
        Index("ix_cleanup_trash_tenant_created", "tenant_id", "created_at"),
    )

    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cleanup_executions.id", ondelete="SET NULL")
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cleanup_rules.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    original_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    trash_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RemoteAgent(TenantRecord, Base):
    __tablename__ = "remote_agents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "installation_id", name="uq_remote_agent_installation"),
        Index("ix_remote_agents_status_seen", "tenant_id", "status", "last_seen_at"),
    )

    installation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    os_version: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    agent_version: Mapped[str] = mapped_column(String(50), nullable=False)
    public_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("remote_agents.id", ondelete="SET NULL")
    )
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class AgentPairingToken(TenantRecord, Base):
    __tablename__ = "agent_pairing_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_agent_pairing_token_hash"),
        Index("ix_agent_pairing_expiry", "expires_at", "used_at"),
    )

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    replace_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("remote_agents.id", ondelete="SET NULL")
    )


class AgentRequestNonce(TenantRecord, Base):
    __tablename__ = "agent_request_nonces"
    __table_args__ = (
        UniqueConstraint("agent_id", "nonce_hash", name="uq_agent_request_nonce"),
        Index("ix_agent_request_nonces_expiry", "expires_at"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("remote_agents.id", ondelete="CASCADE"), nullable=False
    )
    nonce_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentCommand(TenantRecord, Base):
    __tablename__ = "agent_commands"
    __table_args__ = (
        UniqueConstraint("agent_id", "idempotency_key", name="uq_agent_command_idempotency"),
        Index("ix_agent_commands_pending", "agent_id", "status", "expires_at", "created_at"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("remote_agents.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("background_jobs.id", ondelete="SET NULL")
    )
    command_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)


class RemoteServer(TenantRecord, Base):
    __tablename__ = "remote_servers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_remote_server_tenant_name"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    transport: Mapped[str] = mapped_column(String(10), nullable=False, default="legacy")
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("remote_agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    protocol: Mapped[str | None] = mapped_column(String(10), nullable=True)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_path: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    allowlist: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    target_folders: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    target_files: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    config_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    configuration_hash: Mapped[str | None] = mapped_column(String(64))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RemoteStructureValidation(TenantRecord, Base):
    __tablename__ = "remote_structure_validations"
    __table_args__ = (
        Index("ix_remote_structure_validation_server", "tenant_id", "server_id", "created_at"),
    )

    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("remote_servers.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("remote_agents.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("background_jobs.id", ondelete="SET NULL")
    )
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SshHostKey(TenantRecord, Base):
    __tablename__ = "ssh_host_keys"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "host", "port", name="uq_ssh_host_key_tenant_host_port"
        ),
    )

    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(100), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class RemoteCleanupExecution(TenantRecord, Base):
    __tablename__ = "remote_cleanup_executions"
    __table_args__ = (
        Index("ix_remote_cleanup_tenant_started", "tenant_id", "started_at"),
    )

    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("remote_servers.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running")
    targets: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RemoteQuarantineItem(TenantRecord, Base):
    __tablename__ = "remote_quarantine_items"
    __table_args__ = (
        Index("ix_remote_quarantine_tenant_created", "tenant_id", "created_at"),
    )

    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("remote_cleanup_executions.id", ondelete="SET NULL"),
    )
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("remote_servers.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    original_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    quarantine_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    moved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BackgroundJob(TenantRecord, Base):
    __tablename__ = "background_jobs"
    __table_args__ = (
        Index("ix_background_jobs_tenant_status", "tenant_id", "status"),
    )

    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running")
    phase: Mapped[str] = mapped_column(String(100), nullable=False, default="queued")
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    total_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    found_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(TenantRecord, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_tenant_created", "tenant_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
