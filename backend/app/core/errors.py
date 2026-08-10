from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass(slots=True)
class DomainError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


class NotFoundError(DomainError):
    def __init__(self, resource: str, details: dict[str, Any] | None = None):
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message=f"{resource} no encontrado",
            status_code=404,
            details=details,
        )


class ConflictError(DomainError):
    def __init__(self, message: str, *, code: str = "RESOURCE_CONFLICT"):
        super().__init__(code=code, message=message, status_code=409)


class DependencyUnavailableError(DomainError):
    def __init__(self, dependency: str, message: str | None = None):
        super().__init__(
            code="DEPENDENCY_UNAVAILABLE",
            message=message or f"{dependency} no está disponible",
            status_code=503,
            details={"dependency": dependency},
        )


async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    content: dict[str, Any] = {
        "error": {
            "code": exc.code,
            "message": exc.message,
        }
    }
    if exc.details:
        content["error"]["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content=content)
