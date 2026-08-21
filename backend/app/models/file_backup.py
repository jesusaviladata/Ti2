from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.operations import TenantRecord, utcnow


class FileBackupStrategy(str, enum.Enum):
    full = "full"
    incremental = "incremental"
    differential = "differential"


class FileBackupFormat(str, enum.Enum):
    direct = "direct"
    zip64 = "zip64"


class FileBackupFilterKind(str, enum.Enum):
    include = "include"
    exclude = "exclude"


class FileBackupFilterOperator(str, enum.Enum):
    glob = "glob"
    extension = "extension"
    relative_path = "relative_path"


class FileBackupRunStatus(str, enum.Enum):
    queued = "queued"
    preflight = "preflight"
    running = "running"
    completed = "completed"
    completed_with_warnings = "completed_with_warnings"
    retryable = "retryable"
    failed = "failed"
    cancelled = "cancelled"


class FileRestoreStatus(str, enum.Enum):
    queued = "queued"
    simulating = "simulating"
    awaiting_confirmation = "awaiting_confirmation"
    restoring = "restoring"
    completed = "completed"
    completed_with_warnings = "completed_with_warnings"
    failed = "failed"
    cancelled = "cancelled"


def _enum(enum_type: type[enum.Enum], name: str) -> SAEnum:
    return SAEnum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class FileBackupTask(TenantRecord, Base):
    __tablename__ = "file_backup_tasks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_file_backup_task_tenant_id"),
        UniqueConstraint(
            "tenant_id", "agent_id", "name", name="uq_file_backup_task_agent_name"
        ),
        CheckConstraint(
            "retention_full_chains >= 1", name="ck_file_backup_task_retention"
        ),
        Index("ix_file_backup_tasks_tenant_active", "tenant_id", "is_active"),
        Index("ix_file_backup_tasks_tenant_agent", "tenant_id", "agent_id"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("remote_agents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    destination_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_connection_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    strategy: Mapped[FileBackupStrategy] = mapped_column(
        _enum(FileBackupStrategy, "file_backup_strategy"), nullable=False
    )
    format: Mapped[FileBackupFormat] = mapped_column(
        _enum(FileBackupFormat, "file_backup_format"), nullable=False
    )
    schedule: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    timezone_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="America/Mexico_City"
    )
    missed_run_policy: Mapped[str] = mapped_column(
        String(30), nullable=False, default="run_once"
    )
    retention_full_chains: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4
    )
    vss_policy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="preferred"
    )
    verification_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="sha256"
    )
    config_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class FileBackupSource(TenantRecord, Base):
    __tablename__ = "file_backup_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["file_backup_tasks.tenant_id", "file_backup_tasks.id"],
            ondelete="CASCADE",
            name="fk_file_backup_source_tenant_task",
        ),
        UniqueConstraint(
            "tenant_id", "task_id", "path", name="uq_file_backup_source_task_path"
        ),
        Index("ix_file_backup_sources_tenant_task", "tenant_id", "task_id"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    include_subfolders: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class FileBackupFilter(TenantRecord, Base):
    __tablename__ = "file_backup_filters"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["file_backup_tasks.tenant_id", "file_backup_tasks.id"],
            ondelete="CASCADE",
            name="fk_file_backup_filter_tenant_task",
        ),
        UniqueConstraint(
            "tenant_id",
            "task_id",
            "kind",
            "operator",
            "pattern",
            name="uq_file_backup_filter_task_rule",
        ),
        Index("ix_file_backup_filters_tenant_task", "tenant_id", "task_id"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[FileBackupFilterKind] = mapped_column(
        _enum(FileBackupFilterKind, "file_backup_filter_kind"), nullable=False
    )
    operator: Mapped[FileBackupFilterOperator] = mapped_column(
        _enum(FileBackupFilterOperator, "file_backup_filter_operator"), nullable=False
    )
    pattern: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FileBackupChain(TenantRecord, Base):
    __tablename__ = "file_backup_chains"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["file_backup_tasks.tenant_id", "file_backup_tasks.id"],
            ondelete="RESTRICT",
            name="fk_file_backup_chain_tenant_task",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_file_backup_chain_tenant_id"),
        Index("ix_file_backup_chains_tenant_task", "tenant_id", "task_id"),
        Index("ix_file_backup_chains_tenant_status", "tenant_id", "status"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    full_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FileBackupRun(TenantRecord, Base):
    __tablename__ = "file_backup_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["file_backup_tasks.tenant_id", "file_backup_tasks.id"],
            ondelete="RESTRICT",
            name="fk_file_backup_run_tenant_task",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "chain_id"],
            ["file_backup_chains.tenant_id", "file_backup_chains.id"],
            ondelete="RESTRICT",
            name="fk_file_backup_run_tenant_chain",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_run_id"],
            ["file_backup_runs.tenant_id", "file_backup_runs.id"],
            ondelete="RESTRICT",
            name="fk_file_backup_run_tenant_parent",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_file_backup_run_tenant_id"),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_file_backup_run_progress",
        ),
        Index(
            "ix_file_backup_runs_tenant_status_created",
            "tenant_id",
            "status",
            "created_at",
        ),
        Index("ix_file_backup_runs_tenant_task_created", "tenant_id", "task_id", "created_at"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("remote_agents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    chain_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    config_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[FileBackupStrategy] = mapped_column(
        _enum(FileBackupStrategy, "file_backup_run_strategy"), nullable=False
    )
    status: Mapped[FileBackupRunStatus] = mapped_column(
        _enum(FileBackupRunStatus, "file_backup_run_status"), nullable=False
    )
    phase: Mapped[str] = mapped_column(String(40), nullable=False, default="queued")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_total: Mapped[int | None] = mapped_column(BigInteger)
    files_processed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bytes_total: Mapped[int | None] = mapped_column(BigInteger)
    bytes_processed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checkpoint_ref: Mapped[str | None] = mapped_column(String(1024))
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class FileBackupArtifact(TenantRecord, Base):
    __tablename__ = "file_backup_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["file_backup_runs.tenant_id", "file_backup_runs.id"],
            ondelete="RESTRICT",
            name="fk_file_backup_artifact_tenant_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "chain_id"],
            ["file_backup_chains.tenant_id", "file_backup_chains.id"],
            ondelete="RESTRICT",
            name="fk_file_backup_artifact_tenant_chain",
        ),
        UniqueConstraint(
            "tenant_id", "run_id", "location", name="uq_file_backup_artifact_run_location"
        ),
        Index(
            "ix_file_backup_artifacts_tenant_created", "tenant_id", "created_at"
        ),
        Index(
            "ix_file_backup_artifacts_tenant_protected", "tenant_id", "protected"
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    location: Mapped[str] = mapped_column(String(2048), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    manifest_ref: Mapped[str | None] = mapped_column(String(2048))
    manifest_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    protected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    protected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    protected_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class FileRestoreJob(TenantRecord, Base):
    __tablename__ = "file_restore_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "chain_id"],
            ["file_backup_chains.tenant_id", "file_backup_chains.id"],
            ondelete="RESTRICT",
            name="fk_file_restore_job_tenant_chain",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_file_restore_job_tenant_id"),
        Index(
            "ix_file_restore_jobs_tenant_status_created",
            "tenant_id",
            "status",
            "created_at",
        ),
    )

    chain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("remote_agents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[FileRestoreStatus] = mapped_column(
        _enum(FileRestoreStatus, "file_restore_status"), nullable=False
    )
    destination_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    destination_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    selection_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    simulation_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    simulation_hash: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FileRestoreConfirmation(TenantRecord, Base):
    __tablename__ = "file_restore_confirmations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "restore_job_id"],
            ["file_restore_jobs.tenant_id", "file_restore_jobs.id"],
            ondelete="RESTRICT",
            name="fk_file_restore_confirmation_tenant_job",
        ),
        UniqueConstraint(
            "tenant_id", "restore_job_id", name="uq_file_restore_confirmation_job"
        ),
        Index(
            "ix_file_restore_confirmations_tenant_expiry",
            "tenant_id",
            "expires_at",
        ),
    )

    restore_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    simulation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
