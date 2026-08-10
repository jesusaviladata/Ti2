from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import Capability, require_capabilities
from app.core.database import get_db
from app.models.user import User
from app.services.remote_cleanup_service import RemoteCleanupService
from app.services.remote_transport import RemoteCredentials


router = APIRouter()
read_operation = require_capabilities(Capability.OPERATION_READ)
simulate_cleanup = require_capabilities(Capability.CLEANUP_SIMULATE)
execute_cleanup = require_capabilities(Capability.CLEANUP_EXECUTE)
manage_config = require_capabilities(Capability.CONFIG_MANAGE)
purge_cleanup = require_capabilities(Capability.PURGE)
cancel_job = require_capabilities(Capability.JOB_CANCEL)


class ServerBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    protocol: Literal["sftp", "ftp", "ftps"]
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str = Field(min_length=1, max_length=255)
    rutaBase: str
    allowlist: list[str] = Field(min_length=1)


class CredentialsBody(BaseModel):
    password: str = ""
    private_key: str = Field("", alias="privateKey")
    passphrase: str = ""

    model_config = {"populate_by_name": True}

    def credentials(self) -> RemoteCredentials:
        return RemoteCredentials(
            password=self.password,
            private_key=self.private_key,
            passphrase=self.passphrase,
        )


class ListBody(CredentialsBody):
    server_id: str
    path: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(200, alias="pageSize", ge=1, le=1000)


class SimulateBody(CredentialsBody):
    server_id: str
    rule: dict


class ExecuteBody(SimulateBody):
    confirmar: bool = False
    conteo_esperado: int | None = Field(None, alias="conteoEsperado", ge=0)


class RestoreBody(CredentialsBody):
    server_id: str = ""


class PurgeBody(CredentialsBody):
    server_id: str
    ids: list[str] = Field(default_factory=list)
    purge_expired: bool = Field(False, alias="purgarVencidos")


class HostKeyBody(BaseModel):
    host: str
    port: int = Field(22, ge=1, le=65535)


class StructuralBody(SimulateBody):
    max_properties: int = Field(0, alias="maxPropiedades", ge=0)


class StructuralExecuteBody(StructuralBody):
    mode: Literal["cuarentena", "directo"] = Field(alias="modo")
    confirmar: bool = False
    conteo_esperado: int | None = Field(None, alias="conteoEsperado", ge=0)


@router.get("/servers")
async def list_servers(
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    items = await RemoteCleanupService(db).list_servers(str(current_user.tenant_id))
    return {"items": items, "total": len(items)}


@router.post("/servers", status_code=status.HTTP_201_CREATED)
async def create_server(
    body: ServerBody,
    current_user: User = Depends(manage_config),
    db: AsyncSession = Depends(get_db),
):
    return await RemoteCleanupService(db).create_server(
        str(current_user.tenant_id), body.model_dump()
    )


@router.put("/servers/{server_id}")
async def update_server(
    server_id: str,
    body: ServerBody,
    current_user: User = Depends(manage_config),
    db: AsyncSession = Depends(get_db),
):
    return await RemoteCleanupService(db).update_server(
        str(current_user.tenant_id), server_id, body.model_dump()
    )


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    server_id: str,
    current_user: User = Depends(manage_config),
    db: AsyncSession = Depends(get_db),
):
    await RemoteCleanupService(db).delete_server(
        str(current_user.tenant_id), server_id
    )


@router.post("/list")
async def list_directory(
    body: ListBody,
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    return await RemoteCleanupService(db).list_directory(
        str(current_user.tenant_id),
        body.server_id,
        body.credentials(),
        body.path,
        body.page,
        body.page_size,
    )


@router.post("/simulate")
async def simulate(
    body: SimulateBody,
    current_user: User = Depends(simulate_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await RemoteCleanupService(db).simulate(
        str(current_user.tenant_id),
        body.server_id,
        body.credentials(),
        body.rule,
    )


@router.post("/execute")
async def execute(
    body: ExecuteBody,
    current_user: User = Depends(execute_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await RemoteCleanupService(db).execute(
        str(current_user.tenant_id),
        str(current_user.id),
        current_user.full_name or current_user.email,
        body.server_id,
        body.credentials(),
        body.rule,
        body.confirmar,
        body.conteo_esperado,
    )


@router.get("/history")
async def history(
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    items = await RemoteCleanupService(db).history(str(current_user.tenant_id))
    return {"items": items, "total": len(items)}


@router.get("/history/{execution_id}")
async def history_detail(
    execution_id: str,
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    return await RemoteCleanupService(db).history_detail(
        str(current_user.tenant_id), execution_id
    )


@router.get("/quarantine")
async def quarantine(
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    items = await RemoteCleanupService(db).quarantine(str(current_user.tenant_id))
    return {"items": items, "total": len(items)}


@router.post("/quarantine/{item_id}/restore")
async def restore(
    item_id: str,
    body: RestoreBody,
    current_user: User = Depends(execute_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await RemoteCleanupService(db).restore(
        str(current_user.tenant_id), item_id, body.credentials()
    )


@router.post("/quarantine/purge")
async def purge(
    body: PurgeBody,
    current_user: User = Depends(purge_cleanup),
    db: AsyncSession = Depends(get_db),
):
    return await RemoteCleanupService(db).purge(
        str(current_user.tenant_id),
        body.server_id,
        body.credentials(),
        body.ids,
        body.purge_expired,
    )


@router.post("/structural/simulate")
async def structural_simulate(
    body: StructuralBody,
    current_user: User = Depends(simulate_cleanup),
    db: AsyncSession = Depends(get_db),
):
    job_id = await RemoteCleanupService(db).start_structural_job(
        str(current_user.tenant_id),
        str(current_user.id),
        body.server_id,
        body.credentials(),
        body.rule,
        "simulate",
        "cuarentena",
        True,
        None,
        body.max_properties,
    )
    return {"jobId": job_id}


@router.post("/structural/execute")
async def structural_execute(
    body: StructuralExecuteBody,
    current_user: User = Depends(execute_cleanup),
    db: AsyncSession = Depends(get_db),
):
    if body.mode == "directo" and current_user.role.value != "admin":
        from fastapi import HTTPException

        raise HTTPException(403, "La eliminación directa requiere administrador")
    job_id = await RemoteCleanupService(db).start_structural_job(
        str(current_user.tenant_id),
        str(current_user.id),
        body.server_id,
        body.credentials(),
        body.rule,
        "execute",
        body.mode,
        body.confirmar,
        body.conteo_esperado,
        body.max_properties,
    )
    return {"jobId": job_id}


@router.get("/structural/job/{job_id}")
async def structural_job(
    job_id: str,
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    return await RemoteCleanupService(db).job(str(current_user.tenant_id), job_id)


@router.post("/structural/job/{job_id}/cancel")
async def structural_job_cancel(
    job_id: str,
    current_user: User = Depends(cancel_job),
    db: AsyncSession = Depends(get_db),
):
    return await RemoteCleanupService(db).cancel_job(
        str(current_user.tenant_id), job_id
    )


hostkeys_router = APIRouter()


@hostkeys_router.get("")
async def list_host_keys(
    current_user: User = Depends(read_operation),
    db: AsyncSession = Depends(get_db),
):
    items = await RemoteCleanupService(db).list_host_keys(
        str(current_user.tenant_id)
    )
    return {"items": items, "total": len(items)}


@hostkeys_router.post("/forget")
async def forget_host_key(
    body: HostKeyBody,
    current_user: User = Depends(manage_config),
    db: AsyncSession = Depends(get_db),
):
    return await RemoteCleanupService(db).forget_host_key(
        str(current_user.tenant_id), body.host, body.port
    )
