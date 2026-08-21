from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operations import (
    AgentStorageAlert,
    AgentStorageThreshold,
    AgentVolumeState,
    RemoteAgent,
)
from app.repositories.cleanup_repository import tenant_uuid


class AgentStorageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_volumes(self, tenant_id: str):
        result = await self.db.execute(
            select(AgentVolumeState, RemoteAgent)
            .join(RemoteAgent, RemoteAgent.id == AgentVolumeState.agent_id)
            .where(AgentVolumeState.tenant_id == tenant_uuid(tenant_id))
        )
        return list(result.all())

    async def list_alerts(self, tenant_id: str, status: str | None = None):
        statement = (
            select(AgentStorageAlert, RemoteAgent)
            .join(RemoteAgent, RemoteAgent.id == AgentStorageAlert.agent_id)
            .where(AgentStorageAlert.tenant_id == tenant_uuid(tenant_id))
            .order_by(AgentStorageAlert.last_observed_at.desc())
        )
        if status:
            statement = statement.where(AgentStorageAlert.status == status)
        result = await self.db.execute(statement)
        return list(result.all())

    async def get_thresholds(self, tenant_id: str) -> AgentStorageThreshold | None:
        result = await self.db.execute(
            select(AgentStorageThreshold).where(
                AgentStorageThreshold.tenant_id == tenant_uuid(tenant_id)
            )
        )
        return result.scalar_one_or_none()

    async def upsert_thresholds(self, tenant_id: str, values: dict):
        statement = (
            insert(AgentStorageThreshold)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_uuid(tenant_id),
                **values,
            )
            .on_conflict_do_update(
                constraint="uq_agent_storage_threshold_tenant",
                set_=values,
            )
            .returning(AgentStorageThreshold)
        )
        result = await self.db.execute(statement)
        return result.scalar_one()

    async def volume_exists(self, tenant_id: str, agent_id: str, volume_key: str) -> bool:
        result = await self.db.execute(
            select(AgentVolumeState.id).where(
                AgentVolumeState.tenant_id == tenant_uuid(tenant_id),
                AgentVolumeState.agent_id == uuid.UUID(agent_id),
                AgentVolumeState.volume_key == volume_key,
            )
        )
        return result.scalar_one_or_none() is not None

    async def upsert_preference(
        self, tenant_id: str, agent_id: str | None, volume_key: str | None
    ):
        values = {
            "preferred_agent_id": uuid.UUID(agent_id) if agent_id else None,
            "preferred_volume_key": volume_key,
        }
        statement = (
            insert(AgentStorageThreshold)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_uuid(tenant_id),
                **values,
            )
            .on_conflict_do_update(
                constraint="uq_agent_storage_threshold_tenant",
                set_=values,
            )
            .returning(AgentStorageThreshold)
        )
        result = await self.db.execute(statement)
        return result.scalar_one()
