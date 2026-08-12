from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.database import engine


EXPECTED_ALEMBIC_REVISION = "0004"
router = APIRouter(tags=["health"])


async def get_readiness() -> dict:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            result = await connection.execute(
                text("SELECT version_num FROM alembic_version")
            )
            revision = result.scalar_one_or_none()
    except SQLAlchemyError:
        return {"ready": False, "reason": "database_unavailable"}

    if revision != EXPECTED_ALEMBIC_REVISION:
        return {
            "ready": False,
            "reason": "migration_outdated",
            "revision": revision,
        }
    return {"ready": True, "revision": revision}


@router.get("/health")
@router.get("/health/live")
async def liveness():
    return {"status": "alive", "version": settings.API_VERSION}


@router.get("/health/ready")
async def readiness(check: dict = Depends(get_readiness)):
    if not check["ready"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_NOT_READY", "reason": check["reason"]},
        )
    return {"status": "ready", "revision": check["revision"]}
