from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operations import (
    AgentCommand,
    AgentPairingToken,
    AgentRequestNonce,
    BackgroundJob,
    RemoteAgent,
)
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

    async def get_agent_unscoped(self, agent_id: str) -> RemoteAgent | None:
        try:
            parsed_id = uuid.UUID(agent_id)
        except ValueError:
            return None
        result = await self.db.execute(
            select(RemoteAgent).where(RemoteAgent.id == parsed_id)
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

    async def reserve_nonce(
        self,
        agent: RemoteAgent,
        nonce_hash: str,
        expires_at: datetime,
    ) -> bool:
        statement = (
            insert(AgentRequestNonce)
            .values(
                id=uuid.uuid4(),
                tenant_id=agent.tenant_id,
                agent_id=agent.id,
                nonce_hash=nonce_hash,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(constraint="uq_agent_request_nonce")
            .returning(AgentRequestNonce.id)
        )
        result = await self.db.execute(statement)
        return result.scalar_one_or_none() is not None

    async def find_command_by_idempotency(
        self, agent_id: uuid.UUID, idempotency_key: str
    ) -> AgentCommand | None:
        result = await self.db.execute(
            select(AgentCommand).where(
                AgentCommand.agent_id == agent_id,
                AgentCommand.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def claim_next_command(
        self, agent_id: uuid.UUID, now: datetime
    ) -> AgentCommand | None:
        result = await self.db.execute(
            select(AgentCommand)
            .where(
                AgentCommand.agent_id == agent_id,
                AgentCommand.status == "pending",
                AgentCommand.expires_at > now,
            )
            .order_by(AgentCommand.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        command = result.scalar_one_or_none()
        if command is not None:
            command.status = "claimed"
            command.claimed_at = now
            await self.db.flush()
        return command

    async def get_command_for_agent(
        self, agent_id: uuid.UUID, command_id: uuid.UUID
    ) -> AgentCommand | None:
        result = await self.db.execute(
            select(AgentCommand).where(
                AgentCommand.id == command_id,
                AgentCommand.agent_id == agent_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_background_job(
        self, job_id: uuid.UUID
    ) -> BackgroundJob | None:
        result = await self.db.execute(
            select(BackgroundJob).where(BackgroundJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def flush(self) -> None:
        await self.db.flush()
