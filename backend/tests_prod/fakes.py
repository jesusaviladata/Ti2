import secrets
import uuid

from fastapi import HTTPException, status

from app.services.session_store import SessionData


class MemorySessionStore:
    def __init__(self):
        self.sessions: dict[str, dict[str, str]] = {}
        self.failures: dict[str, int] = {}

    async def create(self, user_id: str, tenant_id: str) -> SessionData:
        data = SessionData(str(uuid.uuid4()), str(uuid.uuid4()), secrets.token_urlsafe(32))
        self.sessions[data.sid] = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "refresh_jti": data.refresh_jti,
            "csrf_token": data.csrf_token,
            "revoked": "0",
        }
        return data

    async def validate(self, sid: str, user_id: str) -> bool:
        session = self.sessions.get(sid)
        return bool(session and session["user_id"] == user_id and session["revoked"] == "0")

    async def rotate(self, sid: str, presented_jti: str) -> tuple[str, str]:
        session = self.sessions.get(sid)
        if not session or session["revoked"] != "0" or session["refresh_jti"] != presented_jti:
            if session:
                session["revoked"] = "1"
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesion expirada")
        session["refresh_jti"] = str(uuid.uuid4())
        return session["refresh_jti"], session["csrf_token"]

    async def revoke(self, sid: str) -> None:
        if sid in self.sessions:
            self.sessions[sid]["revoked"] = "1"

    async def login_failures(self, key: str) -> int:
        return self.failures.get(key, 0)

    async def record_login_failure(self, key: str) -> None:
        self.failures[key] = self.failures.get(key, 0) + 1

    async def clear_login_failures(self, key: str) -> None:
        self.failures.pop(key, None)
