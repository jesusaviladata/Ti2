from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.csrf import CSRFMiddleware
from app.core.scheduler import scheduler
from app.core.errors import DomainError, domain_error_handler
from app.middleware.audit import AuditMiddleware
from app.api import agent as agent_api, health
from app.api.v1 import agents, auth, users
from app.api.v1 import cleanup_runtime, remote_cleanup, file_manager
from app.api.v1 import access_runtime, backups_runtime, connections, insights
from app.services.backup_runtime_service import load_backup_schedules
from app.services.cleanup_scheduler import load_cleanup_schedules


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    try:
        await load_backup_schedules()
        await load_cleanup_schedules()
    except Exception:
        logger.exception("No se pudieron rehidratar las programaciones")
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(DomainError, domain_error_handler)
app.add_middleware(AuditMiddleware)
app.add_middleware(CSRFMiddleware)

app.include_router(health.router)
app.include_router(agent_api.router, prefix="/agent/v1", tags=["agent"] )
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"] )
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(cleanup_runtime.router, prefix="/api/v1/cleanup", tags=["cleanup"])
app.include_router(remote_cleanup.router, prefix="/api/v1/cleanup/remote", tags=["remote-cleanup"])
app.include_router(remote_cleanup.hostkeys_router, prefix="/api/v1/ssh/hostkeys", tags=["ssh-hostkeys"])
app.include_router(file_manager.router, prefix="/api/v1/fm", tags=["file-manager"])
app.include_router(backups_runtime.router, prefix="/api/v1/backups", tags=["backups"])
app.include_router(connections.router, prefix="/api/v1/connections", tags=["connections"])
app.include_router(access_runtime.router, prefix="/api/v1/access", tags=["access"])
app.include_router(insights.dashboard_router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(insights.notifications_router, prefix="/api/v1/notifications", tags=["notifications"])
app.include_router(insights.reports_router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(insights.search_router, prefix="/api/v1/search", tags=["search"])
