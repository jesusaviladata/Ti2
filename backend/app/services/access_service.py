from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.access_log import AccessLog
from app.models.user import User
from app.repositories.cleanup_repository import tenant_uuid


def serialize_access(item: AccessLog, user: User | None = None) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "user_id": str(item.user_id),
        "user": user.full_name if user else "",
        "role": user.role.value if user else "",
        "server": item.server_name,
        "ip": item.ip_address,
        "tool": item.tool,
        "reason": item.reason or "",
        "client": item.client_name or "",
        "start": item.started_at.isoformat(),
        "end": item.ended_at.isoformat() if item.ended_at else None,
        "duration_min": item.duration_minutes,
        "status": item.status,
        "notes": item.notes or "",
        "is_suspicious": item.is_suspicious,
    }


class AccessService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _query(self, tenant_id: str):
        return (
            select(AccessLog, User)
            .join(User, User.id == AccessLog.user_id)
            .where(AccessLog.tenant_id == tenant_uuid(tenant_id))
        )

    async def create(
        self, tenant_id: str, user: User, data: dict[str, Any]
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        suspicious = now.hour < 6 or now.hour >= 23
        item = AccessLog(
            tenant_id=tenant_uuid(tenant_id),
            user_id=user.id,
            server_name=data["server"],
            ip_address=data["ip"],
            tool=data["tool"],
            reason=data.get("reason"),
            client_name=data.get("client"),
            notes="",
            status="active",
            is_suspicious=suspicious,
        )
        self.db.add(item)
        await self.db.flush()
        return serialize_access(item, user)

    async def list(
        self, tenant_id: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        query = self._query(tenant_id)
        if status:
            query = query.where(AccessLog.status == status)
        query = query.order_by(AccessLog.started_at.desc())
        rows = (await self.db.execute(query)).all()
        return [serialize_access(item, user) for item, user in rows]

    async def get(
        self, tenant_id: str, item_id: str
    ) -> tuple[AccessLog, User]:
        result = await self.db.execute(
            self._query(tenant_id).where(AccessLog.id == uuid.UUID(item_id))
        )
        row = result.one_or_none()
        if not row:
            raise NotFoundError("Sesión de acceso")
        return row[0], row[1]

    async def close(
        self, tenant_id: str, item_id: str, notes: str
    ) -> dict[str, Any]:
        item, user = await self.get(tenant_id, item_id)
        now = datetime.now(timezone.utc)
        item.ended_at = now
        item.duration_minutes = max(
            0, int((now - item.started_at).total_seconds() // 60)
        )
        item.notes = notes
        item.status = "closed"
        return serialize_access(item, user)

    async def delete(self, tenant_id: str, item_id: str) -> str:
        item, _ = await self.get(tenant_id, item_id)
        await self.db.delete(item)
        return str(item.id)

    async def alerts(self, tenant_id: str) -> list[dict[str, Any]]:
        rows = (
            await self.db.execute(
                self._query(tenant_id)
                .where(AccessLog.is_suspicious.is_(True))
                .order_by(AccessLog.started_at.desc())
            )
        ).all()
        return [serialize_access(item, user) for item, user in rows]

    async def csv_bytes(self, tenant_id: str) -> bytes:
        items = await self.list(tenant_id)
        output = io.StringIO()
        fields = [
            "id",
            "user",
            "role",
            "server",
            "ip",
            "tool",
            "reason",
            "client",
            "start",
            "end",
            "duration_min",
            "status",
            "notes",
            "is_suspicious",
        ]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(items)
        return output.getvalue().encode("utf-8-sig")
