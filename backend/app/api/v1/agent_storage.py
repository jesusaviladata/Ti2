from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import Capability, require_capabilities
from app.core.database import get_db
from app.models.user import User
from app.services.agent_storage_service import AgentStorageService


router = APIRouter()
read_storage = require_capabilities(Capability.OPERATION_READ)
manage_storage = require_capabilities(Capability.CONFIG_MANAGE)


class StorageThresholdRequest(BaseModel):
    warning_free_percent: float = Field(alias="warningFreePercent", gt=0, le=100)
    warning_free_bytes: int = Field(alias="warningFreeBytes", ge=0)
    critical_free_percent: float = Field(alias="criticalFreePercent", gt=0, le=100)
    critical_free_bytes: int = Field(alias="criticalFreeBytes", ge=0)

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def validate_order(self):
        if self.critical_free_percent > self.warning_free_percent:
            raise ValueError("El porcentaje crítico debe ser menor o igual al preventivo")
        if self.critical_free_bytes > self.warning_free_bytes:
            raise ValueError("La reserva crítica debe ser menor o igual a la preventiva")
        return self


@router.get("")
async def storage_inventory(
    current_user: User = Depends(read_storage),
    db: AsyncSession = Depends(get_db),
):
    return await AgentStorageService(db).inventory(str(current_user.tenant_id))


@router.get("/alerts")
async def storage_alerts(
    status: str | None = Query("open", pattern="^(open|resolved)$"),
    current_user: User = Depends(read_storage),
    db: AsyncSession = Depends(get_db),
):
    return await AgentStorageService(db).alerts(str(current_user.tenant_id), status)


@router.put("/thresholds")
async def update_storage_thresholds(
    body: StorageThresholdRequest,
    current_user: User = Depends(manage_storage),
    db: AsyncSession = Depends(get_db),
):
    result = await AgentStorageService(db).update_thresholds(
        str(current_user.tenant_id),
        {
            "warning_free_percent": body.warning_free_percent,
            "warning_free_bytes": body.warning_free_bytes,
            "critical_free_percent": body.critical_free_percent,
            "critical_free_bytes": body.critical_free_bytes,
        },
    )
    await db.commit()
    return result
