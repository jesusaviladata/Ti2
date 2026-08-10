from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.services.session_store import SessionStore

class AuthService:
    def __init__(self, db: AsyncSession, sessions: SessionStore):
        self.db = db
        self.sessions = sessions

    async def _get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def _get_user_by_id(self, user_id: str) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def login(self, email: str, password: str, source_ip: str = "unknown") -> dict:
        email = email.strip().lower()
        rate_key = f"{email}:{source_ip}"
        if await self.sessions.login_failures(rate_key) >= settings.LOGIN_MAX_FAILS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.",
            )

        user = await self._get_user_by_email(email)

        # Always run password verification to prevent timing attacks
        dummy_hash = "$2b$12$yHfEken7UiHj6qrDE27ovuxCwmBDXpMnf9AxRBr0YoBRQaBOqoxZq"
        candidate_hash = user.hashed_password if user else dummy_hash
        password_ok = verify_password(password, candidate_hash)

        if not user or not password_ok:
            await self.sessions.record_login_failure(rate_key)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta desactivada")

        await self.sessions.clear_login_failures(rate_key)


        session = await self.sessions.create(str(user.id), str(user.tenant_id))
        return {
            "access_token": create_access_token(
                str(user.id), tenant_id=str(user.tenant_id), sid=session.sid
            ),
            "refresh_token": create_refresh_token(
                str(user.id),
                tenant_id=str(user.tenant_id),
                sid=session.sid,
                jti=session.refresh_jti,
            ),
            "csrf_token": session.csrf_token,
            "token_type": "bearer",
        }

