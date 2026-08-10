from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.operations import (
    BackgroundJob,
    RemoteCleanupExecution,
    RemoteQuarantineItem,
    RemoteServer,
    SshHostKey,
)
from app.repositories.cleanup_repository import tenant_uuid


class RemoteRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_servers(self, tenant_id: str) -> list[RemoteServer]:
        result = await self.db.execute(
            select(RemoteServer)
            .where(RemoteServer.tenant_id == tenant_uuid(tenant_id))
            .order_by(RemoteServer.name)
        )
        return list(result.scalars().all())

    async def get_server(self, tenant_id: str, server_id: str) -> RemoteServer:
        result = await self.db.execute(
            select(RemoteServer).where(
                RemoteServer.id == uuid.UUID(server_id),
                RemoteServer.tenant_id == tenant_uuid(tenant_id),
            )
        )
        server = result.scalar_one_or_none()
        if not server:
            raise NotFoundError("Servidor remoto")
        return server

    async def get_host_key(
        self, tenant_id: str, host: str, port: int
    ) -> SshHostKey | None:
        result = await self.db.execute(
            select(SshHostKey).where(
                SshHostKey.tenant_id == tenant_uuid(tenant_id),
                SshHostKey.host == host,
                SshHostKey.port == port,
            )
        )
        return result.scalar_one_or_none()

    async def list_host_keys(self, tenant_id: str) -> list[SshHostKey]:
        result = await self.db.execute(
            select(SshHostKey)
            .where(SshHostKey.tenant_id == tenant_uuid(tenant_id))
            .order_by(SshHostKey.host, SshHostKey.port)
        )
        return list(result.scalars().all())

    async def get_quarantine(
        self, tenant_id: str, item_id: str
    ) -> RemoteQuarantineItem:
        result = await self.db.execute(
            select(RemoteQuarantineItem).where(
                RemoteQuarantineItem.id == uuid.UUID(item_id),
                RemoteQuarantineItem.tenant_id == tenant_uuid(tenant_id),
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise NotFoundError("Elemento de cuarentena remota")
        return item

    async def list_quarantine(self, tenant_id: str) -> list[RemoteQuarantineItem]:
        result = await self.db.execute(
            select(RemoteQuarantineItem)
            .where(
                RemoteQuarantineItem.tenant_id == tenant_uuid(tenant_id),
                RemoteQuarantineItem.restored_at.is_(None),
                RemoteQuarantineItem.purged_at.is_(None),
            )
            .order_by(RemoteQuarantineItem.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_executions(
        self, tenant_id: str
    ) -> list[RemoteCleanupExecution]:
        result = await self.db.execute(
            select(RemoteCleanupExecution)
            .where(RemoteCleanupExecution.tenant_id == tenant_uuid(tenant_id))
            .order_by(RemoteCleanupExecution.started_at.desc())
        )
        return list(result.scalars().all())

    async def get_execution(
        self, tenant_id: str, execution_id: str
    ) -> RemoteCleanupExecution:
        result = await self.db.execute(
            select(RemoteCleanupExecution).where(
                RemoteCleanupExecution.id == uuid.UUID(execution_id),
                RemoteCleanupExecution.tenant_id == tenant_uuid(tenant_id),
            )
        )
        execution = result.scalar_one_or_none()
        if not execution:
            raise NotFoundError("Ejecución remota")
        return execution

    async def get_job(self, tenant_id: str, job_id: str) -> BackgroundJob:
        result = await self.db.execute(
            select(BackgroundJob).where(
                BackgroundJob.id == uuid.UUID(job_id),
                BackgroundJob.tenant_id == tenant_uuid(tenant_id),
            )
        )
        job = result.scalar_one_or_none()
        if not job:
            raise NotFoundError("Trabajo")
        return job
