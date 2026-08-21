from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import Capability, require_capabilities
from app.core.database import get_db
from app.models.user import User
from app.services.insights_service import InsightsService


dashboard_router = APIRouter()
notifications_router = APIRouter()
reports_router = APIRouter()
search_router = APIRouter()

read_dashboard = require_capabilities(Capability.DASHBOARD_READ)
read_reports = require_capabilities(Capability.REPORT_READ)
test_notification = require_capabilities(Capability.NOTIFICATION_TEST)


@dashboard_router.get("/summary")
async def summary(
    current_user: User = Depends(read_dashboard),
    db: AsyncSession = Depends(get_db),
):
    return await InsightsService(db).summary(str(current_user.tenant_id))


@dashboard_router.get("/backup-chart")
@dashboard_router.get("/backup-history")
async def backup_chart(
    days: int = Query(default=84, ge=7, le=90),
    current_user: User = Depends(read_dashboard),
    db: AsyncSession = Depends(get_db),
):
    return {
        "chart": await InsightsService(db).backup_chart(
            str(current_user.tenant_id), days=days
        )
    }


@dashboard_router.get("/activity")
async def activity(
    current_user: User = Depends(read_dashboard),
    db: AsyncSession = Depends(get_db),
):
    return {
        "activity": await InsightsService(db).activity(
            str(current_user.tenant_id)
        )
    }


@dashboard_router.get("/metrics")
async def metrics(
    current_user: User = Depends(read_dashboard),
    db: AsyncSession = Depends(get_db),
):
    summary_data = await InsightsService(db).summary(
        str(current_user.tenant_id)
    )
    return {
        "operational": summary_data,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@dashboard_router.get("/alerts")
async def alerts(
    current_user: User = Depends(read_dashboard),
    db: AsyncSession = Depends(get_db),
):
    items = await InsightsService(db).notifications(
        str(current_user.tenant_id), str(current_user.id)
    )
    return {"alerts": items, "total": len(items)}


@dashboard_router.get("/storage-growth")
async def storage_growth(
    current_user: User = Depends(read_dashboard),
    db: AsyncSession = Depends(get_db),
):
    report = await InsightsService(db).backup_report(
        str(current_user.tenant_id)
    )
    return {"totalBytes": report["bytes"], "items": report["items"]}


@notifications_router.get("")
async def notifications(
    current_user: User = Depends(read_dashboard),
    db: AsyncSession = Depends(get_db),
):
    items = await InsightsService(db).notifications(
        str(current_user.tenant_id), str(current_user.id)
    )
    return {"notifications": items, "total": len(items)}


@notifications_router.delete("")
async def clear_notifications(
    current_user: User = Depends(read_dashboard),
    db: AsyncSession = Depends(get_db),
):
    return await InsightsService(db).clear_notifications(
        str(current_user.tenant_id), str(current_user.id)
    )


@notifications_router.post("/test")
async def notification_test(
    current_user: User = Depends(test_notification),
    db: AsyncSession = Depends(get_db),
):
    return await InsightsService(db).create_test_notification(
        str(current_user.tenant_id), str(current_user.id)
    )


@reports_router.get("/backups")
async def backup_report(
    current_user: User = Depends(read_reports),
    db: AsyncSession = Depends(get_db),
):
    return await InsightsService(db).backup_report(str(current_user.tenant_id))


@reports_router.get("/access")
async def access_report(
    current_user: User = Depends(read_reports),
    db: AsyncSession = Depends(get_db),
):
    return await InsightsService(db).access_report(str(current_user.tenant_id))


@reports_router.get("/cleanup")
async def cleanup_report(
    current_user: User = Depends(read_reports),
    db: AsyncSession = Depends(get_db),
):
    return await InsightsService(db).cleanup_report(str(current_user.tenant_id))


@search_router.get("")
async def search(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(read_dashboard),
    db: AsyncSession = Depends(get_db),
):
    items = await InsightsService(db).search(
        str(current_user.tenant_id), q, limit
    )
    return {"items": items, "total": len(items)}
