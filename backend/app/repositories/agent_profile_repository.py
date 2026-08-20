from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operations import AgentConnectionProfile
from app.repositories.cleanup_repository import tenant_uuid


class AgentProfileRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, tenant_id: str, agent_id: uuid.UUID):
        result = await self.db.execute(
            select(AgentConnectionProfile)
            .where(
                AgentConnectionProfile.tenant_id == tenant_uuid(tenant_id),
                AgentConnectionProfile.agent_id == agent_id,
                AgentConnectionProfile.is_active.is_(True),
            )
            .order_by(AgentConnectionProfile.profile_type, AgentConnectionProfile.label)
        )
        return list(result.scalars().all())

    async def get(self, tenant_id: str, agent_id: uuid.UUID, profile_id: str):
        try:
            parsed = uuid.UUID(profile_id)
        except ValueError:
            return None
        result = await self.db.execute(
            select(AgentConnectionProfile).where(
                AgentConnectionProfile.id == parsed,
                AgentConnectionProfile.tenant_id == tenant_uuid(tenant_id),
                AgentConnectionProfile.agent_id == agent_id,
            )
        )
        return result.scalar_one_or_none()

    def add(self, profile: AgentConnectionProfile) -> None:
        self.db.add(profile)
