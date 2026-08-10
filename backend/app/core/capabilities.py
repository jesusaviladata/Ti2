from __future__ import annotations

from enum import StrEnum

from fastapi import Depends, HTTPException, status

from app.core.security import get_current_user
from app.models.user import User, UserRole


class Capability(StrEnum):
    DASHBOARD_READ = "dashboard:read"
    REPORT_READ = "report:read"
    OPERATION_READ = "operation:read"
    CONNECTION_TEST = "connection:test"
    BACKUP_RUN = "backup:run"
    CLEANUP_SIMULATE = "cleanup:simulate"
    CLEANUP_EXECUTE = "cleanup:execute"
    ACCESS_OPERATE = "access:operate"
    FILE_MANAGE = "file:manage"
    JOB_CANCEL = "job:cancel"
    CONFIG_MANAGE = "config:manage"
    USER_MANAGE = "user:manage"
    PURGE = "purge"
    NOTIFICATION_TEST = "notification:test"


_READ_ONLY = {
    Capability.DASHBOARD_READ,
    Capability.REPORT_READ,
    Capability.OPERATION_READ,
}

_OPERATOR = _READ_ONLY | {
    Capability.CONNECTION_TEST,
    Capability.BACKUP_RUN,
    Capability.CLEANUP_SIMULATE,
    Capability.CLEANUP_EXECUTE,
    Capability.ACCESS_OPERATE,
    Capability.FILE_MANAGE,
    Capability.JOB_CANCEL,
}

ROLE_CAPABILITIES: dict[UserRole, frozenset[Capability]] = {
    UserRole.client: frozenset(_READ_ONLY),
    UserRole.technician: frozenset(_OPERATOR),
    UserRole.supervisor: frozenset(_OPERATOR),
    UserRole.admin: frozenset(Capability),
}


def capabilities_for(role: UserRole) -> frozenset[Capability]:
    return ROLE_CAPABILITIES.get(role, frozenset())


def has_capabilities(role: UserRole, *required: Capability) -> bool:
    granted = capabilities_for(role)
    return all(capability in granted for capability in required)


def require_capabilities(*required: Capability):
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if not has_capabilities(current_user.role, *required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INSUFFICIENT_CAPABILITY",
                    "required": [capability.value for capability in required],
                },
            )
        return current_user

    return checker
