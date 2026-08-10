import uuid
from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: str, tenant_id: str) -> User:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
        return user

    async def list_users(self, tenant_id: str, skip: int = 0, limit: int = 50) -> tuple[list[User], int]:
        query = select(User).where(User.tenant_id == tenant_id).offset(skip).limit(limit)
        count_query = select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
        users = (await self.db.execute(query)).scalars().all()
        total = (await self.db.execute(count_query)).scalar_one()
        return list(users), total

    async def create(self, tenant_id: str, data: UserCreate) -> User:
        # Check email uniqueness
        existing = await self.db.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email ya registrado")

        user = User(
            tenant_id=uuid.UUID(tenant_id),
            email=data.email,
            username=data.username,
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
            role=data.role,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def update(self, user_id: str, tenant_id: str, data: UserUpdate) -> User:
        user = await self.get_by_id(user_id, tenant_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        await self.db.flush()
        return user

    async def deactivate(self, user_id: str, tenant_id: str) -> None:
        user = await self.get_by_id(user_id, tenant_id)
        user.is_active = False
        await self.db.flush()

    async def change_password(self, user: User, new_password: str) -> None:
        user.hashed_password = hash_password(new_password)
        await self.db.flush()
