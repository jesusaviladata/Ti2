import hmac

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.cookies import ACCESS_COOKIE, CSRF_COOKIE


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ORIGIN_ONLY_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in SAFE_METHODS or not request.url.path.startswith("/api/"):
            return await call_next(request)

        origin = request.headers.get("origin")
        if origin != settings.APP_ORIGIN:
            return _csrf_error("Origen de solicitud no autorizado")

        uses_access_cookie = bool(request.cookies.get(ACCESS_COOKIE))
        if uses_access_cookie and request.url.path not in ORIGIN_ONLY_PATHS:
            cookie_token = request.cookies.get(CSRF_COOKIE, "")
            header_token = request.headers.get("x-csrf-token", "")
            if not cookie_token or not hmac.compare_digest(cookie_token, header_token):
                return _csrf_error("Token CSRF ausente o invalido")

        return await call_next(request)


def _csrf_error(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": {"code": "AUTH_CSRF_INVALID", "message": message}},
    )
