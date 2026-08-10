from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.session_store import SessionStore, get_session_store

router = APIRouter()


class LoginResponse(BaseModel):
    authenticated: bool


@router.post("/login", response_model=LoginResponse)
async def login(
    response: Response,
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    sessions: SessionStore = Depends(get_session_store),
):
    svc = AuthService(db, sessions)
    source_ip = request.client.host if request.client else "unknown"
    result = await svc.login(form_data.username, form_data.password, source_ip)
    set_auth_cookies(response, result["access_token"], result["refresh_token"], result["csrf_token"])
    return LoginResponse(authenticated=True)







@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    sessions: SessionStore = Depends(get_session_store),
):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesion expirada")
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    svc = AuthService(db, sessions)
    user = await svc._get_user_by_id(payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta desactivada")
    if not payload.get("sid") or not payload.get("jti"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesion expirada")
    new_jti, csrf_token = await sessions.rotate(payload["sid"], payload["jti"])
    set_auth_cookies(
        response,
        create_access_token(
            str(user.id), tenant_id=str(user.tenant_id), sid=payload["sid"]
        ),
        create_refresh_token(
            str(user.id),
            tenant_id=str(user.tenant_id),
            sid=payload["sid"],
            jti=new_jti,
        ),
        csrf_token,
    )
    response.status_code = status.HTTP_204_NO_CONTENT


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    sessions: SessionStore = Depends(get_session_store),
):
    token = request.cookies.get("access_token") or request.cookies.get("refresh_token")
    if token:
        try:
            payload = decode_token(token)
            if payload.get("sid"):
                await sessions.revoke(payload["sid"])
        except HTTPException:
            pass
    clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return {"message": "Sesión cerrada"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "tenantId": str(current_user.tenant_id),
        "email": current_user.email,
        "username": current_user.username,
        "fullName": current_user.full_name,
        "role": current_user.role.value,
        "isActive": current_user.is_active,
    }
