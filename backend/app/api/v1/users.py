from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate
from app.services.user_service import UserService

router = APIRouter()

require_admin = require_roles(UserRole.admin)




class PasswordChangeBody(BaseModel):
    new_password: str = Field(min_length=14, max_length=128)


@router.get("", response_model=dict)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    svc = UserService(db)
    users, total = await svc.list_users(str(current_user.tenant_id), skip, limit)
    return {
        "items": [_serialize(u) for u in users],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post("", response_model=dict, status_code=201)
async def create_user(
    data: UserCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    svc = UserService(db)
    user = await svc.create(str(current_user.tenant_id), data)
    await db.commit()
    return _serialize(user)


@router.get("/{user_id}", response_model=dict)
async def get_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    svc = UserService(db)
    user = await svc.get_by_id(user_id, str(current_user.tenant_id))
    return _serialize(user)


@router.put("/{user_id}", response_model=dict)
async def update_user(
    user_id: str,
    data: UserUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == str(current_user.id) and (
        data.role is not None or data.is_active is False
    ):
        raise HTTPException(
            status_code=400,
            detail="No puedes cambiar tu propio rol ni desactivar tu cuenta",
        )
    svc = UserService(db)
    user = await svc.update(user_id, str(current_user.tenant_id), data)
    await db.commit()
    return _serialize(user)


@router.delete("/{user_id}", status_code=204)
async def deactivate_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == str(current_user.id):
        raise HTTPException(
            status_code=400,
            detail="No puedes desactivar tu propia cuenta",
        )
    svc = UserService(db)
    await svc.deactivate(user_id, str(current_user.tenant_id))
    await db.commit()


@router.post("/{user_id}/change-password", status_code=204)
async def change_password(
    user_id: str,
    body: PasswordChangeBody,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    svc = UserService(db)
    user = await svc.get_by_id(user_id, str(current_user.tenant_id))
    await svc.change_password(user, body.new_password)
    await db.commit()


def _serialize(user: User) -> dict:
    return {
        "id": str(user.id),
        "tenantId": str(user.tenant_id),
        "email": user.email,
        "username": user.username,
        "fullName": user.full_name,
        "role": user.role.value,
        "isActive": user.is_active,
    }
