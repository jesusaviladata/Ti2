from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operations import AgentPairingToken, RemoteAgent
from app.repositories.cleanup_repository import tenant_uuid


class AgentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_agents(self, tenant_id: str) -> list[RemoteAgent]:
        result = await self.db.execute(
            select(RemoteAgent)
            .where(RemoteAgent.tenant_id == tenant_uuid(tenant_id))
            .order_by(RemoteAgent.hostname, RemoteAgent.created_at)
        )
        return list(result.scalars().all())

    async def get_agent(self, tenant_id: str, agent_id: str) -> RemoteAgent | None:
        try:
            parsed_id = uuid.UUID(agent_id)
        except ValueError:
            return None
        result = await self.db.execute(
            select(RemoteAgent).where(
                RemoteAgent.id == parsed_id,
                RemoteAgent.tenant_id == tenant_uuid(tenant_id),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_installation(
        self, tenant_id: str, installation_id: str
    ) -> RemoteAgent | None:
        result = await self.db.execute(
            select(RemoteAgent).where(
                RemoteAgent.tenant_id == tenant_uuid(tenant_id),
                RemoteAgent.installation_id == installation_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_pairing_for_update(
        self, token_hash: str
    ) -> AgentPairingToken | None:
        result = await self.db.execute(
            select(AgentPairingToken)
            .where(AgentPairingToken.token_hash == token_hash)
            .with_for_update()
        )
        return result.scalar_one_or_none()

