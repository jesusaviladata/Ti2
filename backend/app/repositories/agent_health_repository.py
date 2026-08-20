from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operations import AgentStorageAlert, AgentVolumeState, RemoteAgent
from app.schemas.agent import AgentVolumePayload


class AgentHealthRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_volume(
        self,
        *,
        agent: RemoteAgent,
        volume: AgentVolumePayload,
        observed_at: datetime,
    ) -> None:
        values = {
            "id": uuid.uuid4(),
            "tenant_id": agent.tenant_id,
            "agent_id": agent.id,
            "volume_key": volume.volume_key,
            "label": volume.label,
            "mount_point": volume.mount_point,
            "total_bytes": volume.total_bytes,
            "free_bytes": volume.free_bytes,
            "used_percent": volume.used_percent,
            "roles": list(dict.fromkeys(volume.roles)),
            "observed_at": observed_at,
            "error": volume.error,
        }
        statement = insert(AgentVolumeState).values(**values)
        statement = statement.on_conflict_do_update(
            constraint="uq_agent_volume_state_agent_volume",
            set_={
                key: getattr(statement.excluded, key)
                for key in values
                if key not in {"id", "tenant_id", "agent_id", "volume_key"}
            },
        )
        await self.db.execute(statement)

    async def get_open_alert(
        self, *, agent: RemoteAgent, volume_key: str
    ) -> AgentStorageAlert | None:
        result = await self.db.execute(
            select(AgentStorageAlert)
            .where(
                AgentStorageAlert.tenant_id == agent.tenant_id,
                AgentStorageAlert.agent_id == agent.id,
                AgentStorageAlert.volume_key == volume_key,
                AgentStorageAlert.status == "open",
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    def add_alert(self, alert: AgentStorageAlert) -> None:
        self.db.add(alert)
