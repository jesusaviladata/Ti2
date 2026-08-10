from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import Capability, require_capabilities
from app.core.database import get_db
from app.models.user import User
from app.services.file_manager_service import FileManagerService


router = APIRouter()
read_operation = require_capabilities(Capability.OPERATION_READ)
manage_files = require_capabilities(Capability.FILE_MANAGE)


class ConnectionBody(BaseModel):
    host: str
    port: int = Field(ge=1, le=65535)
    protocol: Literal["sftp", "ftp", "ftps"]
    username: str
    password: str = ""
    privateKey: str = ""
    passphrase: str = ""


class PathBody(BaseModel):
    connection: ConnectionBody | None = None
    path: str


class DeleteBody(PathBody):
    contents_only: bool = False


def _connection(body: ConnectionBody | None) -> dict | None:
    return body.model_dump() if body else None


@router.post("/test")
async def test_connection(
    body: ConnectionBody | None = None,
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    return await FileManagerService(db).test(
        str(current_user.tenant_id), _connection(body)
    )


@router.post("/list")
async def list_path(
    body: PathBody,
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    return await FileManagerService(db).list(
        str(current_user.tenant_id), _connection(body.connection), body.path
    )


@router.post("/delete")
async def delete_path(
    body: DeleteBody,
    current_user: User = Depends(manage_files),
    db: AsyncSession = Depends(get_db),
):
    return await FileManagerService(db).delete(
        str(current_user.tenant_id),
        _connection(body.connection),
        body.path,
        body.contents_only,
    )


@router.post("/mkdir")
async def create_directory(
    body: PathBody,
    current_user: User = Depends(manage_files),
    db: AsyncSession = Depends(get_db),
):
    return await FileManagerService(db).mkdir(
        str(current_user.tenant_id), _connection(body.connection), body.path
    )
