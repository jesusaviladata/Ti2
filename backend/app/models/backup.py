import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BackupType(str, enum.Enum):
    full = "full"
    differential = "differential"
    incremental = "incremental"
    log = "log"


class BackupStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class BackupDestination(str, enum.Enum):
    local = "local"
    nas = "nas"
    secondary_server = "secondary_server"
    private_cloud = "private_cloud"


class Backup(Base):
    __tablename__ = "backups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    database_name: Mapped[str] = mapped_column(String(255), nullable=False)
    backup_type: Mapped[BackupType] = mapped_column(SAEnum(BackupType), nullable=False)
    status: Mapped[BackupStatus] = mapped_column(SAEnum(BackupStatus), nullable=False, default=BackupStatus.pending)
    destination: Mapped[BackupDestination] = mapped_column(SAEnum(BackupDestination), nullable=False, default=BackupDestination.local)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
