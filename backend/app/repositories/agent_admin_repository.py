from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operations import AgentCommand, BackgroundJob, RemoteServer
from app.repositories.cleanup_repository import tenant_uuid


class AgentAdminRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_job(self, tenant_id: str, job_id: str) -> BackgroundJob | None:
        try:
            parsed_id = uuid.UUID(job_id)
        except ValueError:
            return None
        result = await self.db.execute(
            select(BackgroundJob).where(
                BackgroundJob.id == parsed_id,
                BackgroundJob.tenant_id == tenant_uuid(tenant_id),
            )
        )
        return result.scalar_one_or_none()

    async def get_command_for_job(self, job_id: uuid.UUID) -> AgentCommand | None:
        result = await self.db.execute(
            select(AgentCommand).where(AgentCommand.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_server(
        self, tenant_id: str, server_id: str
    ) -> RemoteServer | None:
        try:
            parsed_id = uuid.UUID(server_id)
        except ValueError:
            return None
        result = await self.db.execute(
            select(RemoteServer).where(
                RemoteServer.id == parsed_id,
                RemoteServer.tenant_id == tenant_uuid(tenant_id),
            )
        )
        return result.scalar_one_or_none()

    async def get_server_for_agent(
        self, tenant_id: str, agent_id: str
    ) -> RemoteServer | None:
        try:
            parsed_id = uuid.UUID(agent_id)
        except ValueError:
            return None
        result = await self.db.execute(
            select(RemoteServer).where(
                RemoteServer.agent_id == parsed_id,
                RemoteServer.tenant_id == tenant_uuid(tenant_id),
                RemoteServer.transport == "agent",
            )
        )
        return result.scalar_one_or_none()
