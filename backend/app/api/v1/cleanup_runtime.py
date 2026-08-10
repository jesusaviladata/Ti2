from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import Capability, require_capabilities
from app.core.database import get_db
from app.models.user import User
from app.services.cleanup_service import CleanupService


router = APIRouter()

read_cleanup = require_capabilities(Capability.OPERATION_READ)
simulate_cleanup = require_capabilities(Capability.CLEANUP_SIMULATE)
execute_cleanup = require_capabilities(Capability.CLEANUP_EXECUTE)
manage_cleanup = require_capabilities(Capability.CONFIG_MANAGE)
purge_cleanup = require_capabilities(Capability.PURGE)


class FolderBody(BaseModel):
    path: str
    label: str = ""


class RuleBody(BaseModel):
    name: str = ""
    folder_id: str | None = Field(None, alias="folderId")
    patterns: list[str] = Field(default_factory=lambda: ["*"])
    extensions: list[str] = Field(default_factory=list)
    keep: Literal["latest", "latest_n", "none", "all"] = "latest"
    keep_n: int = Field(1, alias="keepN", ge=0)
    min_age_days: float = Field(0, alias="minAgeDays", ge=0)
    enabled: bool = True

    model_config = {"populate_by_name": True}


class RuleUpdateBody(BaseModel):
    name: str | None = None
    folder_id: str | None = Field(None, alias="folderId")
    patterns: list[str] | None = None
    extensions: list[str] | None = None
    keep: Literal["latest", "latest_n", "none", "all"] | None = None
    keep_n: int | None = Field(None, alias="keepN", ge=0)
    min_age_days: float | None = Field(None, alias="minAgeDays", ge=0)
    enabled: bool | None = None

    model_config = {"populate_by_name": True}


class ExecuteBody(BaseModel):
    file_paths: list[str] = Field(default_factory=list)
    rule_id: str | None = None
    simulation_id: str | None = None


class ScheduleBody(BaseModel):
    name: str
    folder_id: str = Field(alias="folderId")
    rule_id: str = Field(alias="ruleId")
    cron_expression: str = Field(alias="cronExpr")
    enabled: bool = True

    model_config = {"populate_by_name": True}


class ScheduleUpdateBody(BaseModel):
    name: str | None = None
    cron_expression: str | None = Field(None, alias="cronExpr")
    enabled: bool | None = None

    model_config = {"populate_by_name": True}


def _body(model: BaseModel, *, exclude_unset: bool = False) -> dict[str, Any]:
    return model.model_dump(by_alias=True, exclude_unset=exclude_unset)


@router.get("/folders")
async def list_folders(
    current_user: User = Depends(read_cleanup),
    db: AsyncSession = Depends(get_db),
):
    items = await CleanupService(db).list_folders(str(current_user.tenant_id))
    return {"items": items, "total": len(items)}


@router.post("/folders", status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: FolderBody,
    current_user: User = Depends(manage_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await CleanupService(db).create_folder(
        str(current_user.tenant_id), body.path, body.label
    )


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: str,
    current_user: User = Depends(manage_cleanup),
    db: AsyncSession = Depends(get_db),
):
    await CleanupService(db).delete_folder(str(current_user.tenant_id), folder_id)


@router.get("/rules")
async def list_rules(
    current_user: User = Depends(read_cleanup),
    db: AsyncSession = Depends(get_db),
):
    items = await CleanupService(db).list_rules(str(current_user.tenant_id))
    return {"items": items, "total": len(items)}


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleBody,
    current_user: User = Depends(manage_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await CleanupService(db).create_rule(
        str(current_user.tenant_id), _body(body)
    )


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    body: RuleUpdateBody,
    current_user: User = Depends(manage_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await CleanupService(db).update_rule(
        str(current_user.tenant_id), rule_id, _body(body, exclude_unset=True)
    )


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: str,
    current_user: User = Depends(manage_cleanup),
    db: AsyncSession = Depends(get_db),
):
    await CleanupService(db).delete_rule(str(current_user.tenant_id), rule_id)


@router.get("/scan")
async def scan(
    folder_id: str | None = Query(None),
    current_user: User = Depends(simulate_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await CleanupService(db).scan(
        str(current_user.tenant_id), str(current_user.id), folder_id
    )


@router.post("/execute")
async def execute(
    body: ExecuteBody,
    current_user: User = Depends(execute_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await CleanupService(db).execute(
        str(current_user.tenant_id),
        str(current_user.id),
        body.file_paths,
        body.simulation_id,
    )


@router.get("/trash")
async def list_trash(
    current_user: User = Depends(read_cleanup),
    db: AsyncSession = Depends(get_db),
):
    items = await CleanupService(db).list_trash(str(current_user.tenant_id))
    return {"items": items, "total": len(items)}


@router.delete("/trash/{item_id}")
async def purge_trash(
    item_id: str,
    current_user: User = Depends(purge_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await CleanupService(db).purge(str(current_user.tenant_id), item_id)


@router.post("/restore/{item_id}")
async def restore_trash(
    item_id: str,
    current_user: User = Depends(execute_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await CleanupService(db).restore(str(current_user.tenant_id), item_id)


@router.get("/history")
async def history(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(read_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await CleanupService(db).history(
        str(current_user.tenant_id), skip, limit
    )


@router.get("/schedules")
async def list_schedules(
    current_user: User = Depends(read_cleanup),
    db: AsyncSession = Depends(get_db),
):
    items = await CleanupService(db).list_schedules(str(current_user.tenant_id))
    return {"items": items, "total": len(items)}


@router.post("/schedules", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleBody,
    current_user: User = Depends(manage_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await CleanupService(db).create_schedule(
        str(current_user.tenant_id), _body(body)
    )


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdateBody,
    current_user: User = Depends(manage_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await CleanupService(db).update_schedule(
        str(current_user.tenant_id),
        schedule_id,
        _body(body, exclude_unset=True),
    )


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: str,
    current_user: User = Depends(manage_cleanup),
    db: AsyncSession = Depends(get_db),
):
    await CleanupService(db).delete_schedule(
        str(current_user.tenant_id), schedule_id
    )
