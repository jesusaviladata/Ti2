import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentBackupPlan(Base):
    __tablename__ = "agent_backup_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("remote_agents.id", ondelete="CASCADE"), nullable=False, index=True)
    sql_profile_id: Mapped[str] = mapped_column(String(128), nullable=False)
    destination_profile_id: Mapped[str | None] = mapped_column(String(128))
    database_names: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    full_days: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)
    differential_days: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)
    hour_utc: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
