from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import Capability, require_capabilities
from app.core.database import get_db
from app.core.errors import DomainError
from app.models.user import User
from app.schemas.file_backup import (
    FileBackupArtifactPatch,
    FileBackupArtifactResponse,
    FileBackupChainResponse,
    FileBackupRunCreate,
    FileBackupRunPage,
    FileBackupRunResponse,
    FileBackupSimulationResponse,
    FileBackupTaskCreate,
    FileBackupTaskPage,
    FileBackupTaskResponse,
    FileBackupTaskUpdate,
    FileRestoreConfirmationCreate,
    FileRestoreCreate,
    FileRestoreResponse,
)
from app.services.file_backup_service import FileBackupService


router = APIRouter()
read_file_backups = require_capabilities(Capability.FILE_BACKUP_READ)
manage_file_backups = require_capabilities(Capability.FILE_BACKUP_MANAGE)
run_file_backups = require_capabilities(Capability.FILE_BACKUP_RUN)
cancel_file_backups = require_capabilities(Capability.FILE_BACKUP_CANCEL)
protect_file_backups = require_capabilities(Capability.FILE_BACKUP_PROTECT)
restore_file_backups = require_capabilities(Capability.FILE_BACKUP_RESTORE)


def _not_ready() -> None:
    raise DomainError(
        "FILE_BACKUP_NOT_AVAILABLE",
        "El módulo de respaldo de archivos aún no está habilitado",
        503,
    )


@router.get("/tasks", response_model=FileBackupTaskPage)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    agent_id: uuid.UUID | None = Query(None, alias="agentId"),
    active: bool | None = None,
    search: str | None = Query(None, max_length=255),
    current_user: User = Depends(read_file_backups),
    db: AsyncSession = Depends(get_db),
):
    return await FileBackupService(db).list(
        str(current_user.tenant_id),
        page=page,
        page_size=page_size,
        agent_id=agent_id,
        active=active,
        search=search,
    )


@router.post("/tasks", response_model=FileBackupTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: FileBackupTaskCreate,
    current_user: User = Depends(manage_file_backups),
    db: AsyncSession = Depends(get_db),
):
    result = await FileBackupService(db).create(str(current_user.tenant_id), body)
    await db.commit()
    return result


@router.get("/tasks/{task_id}", response_model=FileBackupTaskResponse)
async def get_task(
    task_id: uuid.UUID,
    current_user: User = Depends(read_file_backups),
    db: AsyncSession = Depends(get_db),
):
    return await FileBackupService(db).get(str(current_user.tenant_id), task_id)


@router.patch("/tasks/{task_id}", response_model=FileBackupTaskResponse)
async def update_task(
    task_id: uuid.UUID,
    body: FileBackupTaskUpdate,
    current_user: User = Depends(manage_file_backups),
    db: AsyncSession = Depends(get_db),
):
    result = await FileBackupService(db).update(
        str(current_user.tenant_id), task_id, body
    )
    await db.commit()
    return result


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    current_user: User = Depends(manage_file_backups),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await FileBackupService(db).delete(str(current_user.tenant_id), task_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/tasks/{task_id}/simulations",
    response_model=FileBackupSimulationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_simulation(
    task_id: uuid.UUID,
    current_user: User = Depends(run_file_backups),
    db: AsyncSession = Depends(get_db),
):
    result = await FileBackupService(db).create_simulation(
        str(current_user.tenant_id), task_id
    )
    await db.commit()
    return result


@router.get("/simulations/{simulation_id}", response_model=FileBackupSimulationResponse)
async def get_simulation(
    simulation_id: uuid.UUID,
    current_user: User = Depends(read_file_backups),
    db: AsyncSession = Depends(get_db),
):
    return await FileBackupService(db).get_simulation(
        str(current_user.tenant_id), simulation_id
    )


@router.get("/tasks/{task_id}/runs", response_model=FileBackupRunPage)
async def list_runs(
    task_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    current_user: User = Depends(read_file_backups),
    db: AsyncSession = Depends(get_db),
):
    return await FileBackupService(db).list_runs(
        str(current_user.tenant_id),
        task_id,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/tasks/{task_id}/runs",
    response_model=FileBackupRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_run(
    task_id: uuid.UUID,
    body: FileBackupRunCreate,
    current_user: User = Depends(run_file_backups),
    db: AsyncSession = Depends(get_db),
):
    result = await FileBackupService(db).create_run(
        str(current_user.tenant_id), task_id, body
    )
    await db.commit()
    return result


@router.get("/runs/{run_id}", response_model=FileBackupRunResponse)
async def get_run(
    run_id: uuid.UUID,
    current_user: User = Depends(read_file_backups),
    db: AsyncSession = Depends(get_db),
):
    return await FileBackupService(db).get_run(str(current_user.tenant_id), run_id)


@router.post("/runs/{run_id}/cancellations", status_code=status.HTTP_202_ACCEPTED)
async def cancel_run(
    run_id: uuid.UUID,
    current_user: User = Depends(cancel_file_backups),
):
    _not_ready()


@router.post("/restores", response_model=FileRestoreResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_restore(
    body: FileRestoreCreate,
    current_user: User = Depends(restore_file_backups),
):
    _not_ready()


@router.get("/restores/{restore_id}", response_model=FileRestoreResponse)
async def get_restore(
    restore_id: uuid.UUID,
    current_user: User = Depends(read_file_backups),
):
    _not_ready()


@router.post(
    "/restores/{restore_id}/confirmations",
    response_model=FileRestoreResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def confirm_restore(
    restore_id: uuid.UUID,
    body: FileRestoreConfirmationCreate,
    current_user: User = Depends(restore_file_backups),
):
    _not_ready()


@router.get("/chains/{chain_id}", response_model=FileBackupChainResponse)
async def get_chain(
    chain_id: uuid.UUID,
    current_user: User = Depends(read_file_backups),
):
    _not_ready()


@router.patch("/artifacts/{artifact_id}", response_model=FileBackupArtifactResponse)
async def update_artifact(
    artifact_id: uuid.UUID,
    body: FileBackupArtifactPatch,
    current_user: User = Depends(protect_file_backups),
    db: AsyncSession = Depends(get_db),
):
    result = await FileBackupService(db).set_artifact_protection(
        str(current_user.tenant_id),
        artifact_id,
        protected=body.protected,
        user_id=current_user.id,
    )
    await db.commit()
    return result
