from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


AGENT_MODULE_SETTINGS_ID = 1


class AgentModuleSetting(Base):
    """Estado del modulo de agentes para toda la instalacion (fila unica).

    La llave privada de firma de comandos se guarda cifrada con una clave derivada de
    SECRET_KEY; nunca se expone por la API. La llave publica y su keyId son publicos:
    viajan en el bootstrap.json del paquete del agente.
    """

    __tablename__ = "agent_module_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_agent_module_settings_singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=AGENT_MODULE_SETTINGS_ID)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    signing_key_id: Mapped[str | None] = mapped_column(String(64))
    signing_public_key: Mapped[str | None] = mapped_column(String(128))
    signing_private_key_encrypted: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
