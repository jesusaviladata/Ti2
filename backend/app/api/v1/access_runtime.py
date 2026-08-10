from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import (
    Capability,
    capabilities_for,
    require_capabilities,
)
from app.core.database import get_db
from app.models.user import User, UserRole
from app.services.access_service import AccessService


router = APIRouter()
read_access = require_capabilities(Capability.OPERATION_READ)
operate_access = require_capabilities(Capability.ACCESS_OPERATE)
manage_access = require_capabilities(Capability.CONFIG_MANAGE)


class CreateSessionBody(BaseModel):
    server: str = Field(min_length=1, max_length=255)
    ip: str = Field(min_length=1, max_length=45)
    tool: str = Field(min_length=1, max_length=50)
    reason: str = Field("", max_length=512)
    client: str = Field("", max_length=255)
    engineer: str = Field("", max_length=255)


class CloseSessionBody(BaseModel):
    notes: str = Field("", max_length=2048)


class PermissionBody(BaseModel):
    role: UserRole


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionBody,
    current_user: User = Depends(operate_access),
    db: AsyncSession = Depends(get_db),
):
    return await AccessService(db).create(
        str(current_user.tenant_id), current_user, body.model_dump()
    )


@router.get("/sessions")
async def list_sessions(
    status_filter: str = Query("active", alias="status"),
    current_user: User = Depends(read_access),
    db: AsyncSession = Depends(get_db),
):
    items = await AccessService(db).list(
        str(current_user.tenant_id), status_filter
    )
    return {"sessions": items}


@router.put("/sessions/{session_id}/close")
async def close_session(
    session_id: str,
    body: CloseSessionBody,
    current_user: User = Depends(operate_access),
    db: AsyncSession = Depends(get_db),
):
    return await AccessService(db).close(
        str(current_user.tenant_id), session_id, body.notes
    )


@router.delete("/sessions/{session_id}/delete")
async def delete_session(
    session_id: str,
    current_user: User = Depends(manage_access),
    db: AsyncSession = Depends(get_db),
):
    deleted = await AccessService(db).delete(
        str(current_user.tenant_id), session_id
    )
    return {"deleted": deleted}


@router.get("/logs")
async def access_logs(
    current_user: User = Depends(read_access),
    db: AsyncSession = Depends(get_db),
):
    return {"logs": await AccessService(db).list(str(current_user.tenant_id))}


@router.get("/logs/{log_id}")
async def access_log_detail(
    log_id: str,
    current_user: User = Depends(read_access),
    db: AsyncSession = Depends(get_db),
):
    item, user = await AccessService(db).get(str(current_user.tenant_id), log_id)
    from app.services.access_service import serialize_access

    return serialize_access(item, user)


@router.get("/alerts")
async def suspicious_access(
    current_user: User = Depends(read_access),
    db: AsyncSession = Depends(get_db),
):
    return {
        "alerts": await AccessService(db).alerts(str(current_user.tenant_id))
    }


@router.get("/download")
async def download_access_log(
    current_user: User = Depends(read_access),
    db: AsyncSession = Depends(get_db),
):
    content = await AccessService(db).csv_bytes(str(current_user.tenant_id))
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="access-log.csv"'
        },
    )


@router.post("/permissions")
async def role_permissions(
    body: PermissionBody,
    _: User = Depends(manage_access),
):
    return {
        "role": body.role.value,
        "capabilities": sorted(
            capability.value for capability in capabilities_for(body.role)
        ),
    }
