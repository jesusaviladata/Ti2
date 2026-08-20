from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import Capability, require_capabilities
from app.core.database import get_db
from app.models.user import User
from app.services.agent_profile_service import AgentProfileService, serialize_managed_profile


router = APIRouter()
read_profiles = require_capabilities(Capability.OPERATION_READ)
manage_profiles = require_capabilities(Capability.CONFIG_MANAGE)
test_profiles = require_capabilities(Capability.CONNECTION_TEST)


class ManagedProfileBody(BaseModel):
    profile_type: str = Field(alias="profileType", pattern="^(sql|destination)$")
    profile_key: str | None = Field(None, alias="profileKey", min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    public_config: dict = Field(alias="publicConfig")
    secret: dict | None = None

    model_config = {"populate_by_name": True, "extra": "forbid"}


@router.get("/{agent_id}/managed-profiles")
async def list_managed_profiles(
    agent_id: str,
    current_user: User = Depends(read_profiles),
    db: AsyncSession = Depends(get_db),
):
    return await AgentProfileService(db).list(str(current_user.tenant_id), agent_id)


@router.post("/{agent_id}/managed-profiles", status_code=status.HTTP_201_CREATED)
async def create_managed_profile(
    agent_id: str,
    body: ManagedProfileBody,
    current_user: User = Depends(manage_profiles),
    db: AsyncSession = Depends(get_db),
):
    item = await AgentProfileService(db).save(
        str(current_user.tenant_id), agent_id, profile_id=None, **body.model_dump()
    )
    await db.commit()
    return serialize_managed_profile(item)


@router.put("/{agent_id}/managed-profiles/{profile_id}")
async def update_managed_profile(
    agent_id: str,
    profile_id: str,
    body: ManagedProfileBody,
    current_user: User = Depends(manage_profiles),
    db: AsyncSession = Depends(get_db),
):
    item = await AgentProfileService(db).save(
        str(current_user.tenant_id), agent_id, profile_id=profile_id, **body.model_dump()
    )
    await db.commit()
    return serialize_managed_profile(item)


@router.delete("/{agent_id}/managed-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_managed_profile(
    agent_id: str,
    profile_id: str,
    current_user: User = Depends(manage_profiles),
    db: AsyncSession = Depends(get_db),
):
    await AgentProfileService(db).delete(str(current_user.tenant_id), agent_id, profile_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{agent_id}/managed-profiles/discover", status_code=status.HTTP_202_ACCEPTED)
async def discover_agent_environment(
    agent_id: str,
    current_user: User = Depends(manage_profiles),
    db: AsyncSession = Depends(get_db),
):
    job = await AgentProfileService(db).start_job(
        str(current_user.tenant_id), agent_id, profile_id=None, kind="agent_environment_discovery"
    )
    await db.commit()
    return {"jobId": str(job.id)}


@router.post("/{agent_id}/managed-profiles/{profile_id}/test", status_code=status.HTTP_202_ACCEPTED)
async def test_managed_profile(
    agent_id: str,
    profile_id: str,
    current_user: User = Depends(test_profiles),
    db: AsyncSession = Depends(get_db),
):
    job = await AgentProfileService(db).start_job(
        str(current_user.tenant_id), agent_id, profile_id=profile_id, kind="agent_profile_test"
    )
    await db.commit()
    return {"jobId": str(job.id)}
