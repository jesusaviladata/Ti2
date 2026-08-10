from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.capabilities import Capability, require_capabilities
from app.models.user import User
from app.services.connection_service import ConnectionService


router = APIRouter()
test_connection = require_capabilities(Capability.CONNECTION_TEST)


class ConnectionBody(BaseModel):
    server: str = Field(min_length=1, max_length=255)
    port: int = Field(1433, ge=1, le=65535)
    authentication: Literal["sql", "windows"] = "sql"
    username: str = ""
    password: str = ""
    driver: str = "ODBC Driver 17 for SQL Server"


@router.post("/test")
async def test(
    body: ConnectionBody,
    _: User = Depends(test_connection),
):
    return await ConnectionService().test(body.model_dump())


@router.post("/databases")
async def databases(
    body: ConnectionBody,
    _: User = Depends(test_connection),
):
    return await ConnectionService().databases(body.model_dump())
