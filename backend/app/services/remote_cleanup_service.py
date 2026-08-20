from __future__ import annotations

import asyncio
import posixpath
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.errors import ConflictError, DomainError
from app.models.operations import (
    BackgroundJob,
    RemoteCleanupExecution,
    RemoteQuarantineItem,
    RemoteServer,
    SshHostKey,
)
from app.repositories.cleanup_repository import tenant_uuid
from app.repositories.remote_repository import RemoteRepository
from app.services.remote_transport import (
    RemoteCredentials,
    RemoteServerConfig,
    open_remote_client,
    probe_ssh_host_key,
    validate_remote_path,
)
from remote_cleanup import quarantine_path, select_candidates
from structural_cleanup import select_structural


def _server_payload(server: RemoteServer) -> dict[str, Any]:
    return {
        "id": str(server.id),
        "name": server.name,
        "transport": server.transport,
        "agentId": str(server.agent_id) if server.agent_id else None,
        "protocol": server.protocol,
        "host": server.host,
        "port": server.port,
        "username": server.username,
        "rutaBase": server.base_path,
        "allowlist": server.allowlist,
        "targetFolders": server.target_folders,
        "targetFiles": server.target_files,
        "createdAt": server.created_at.isoformat(),
    }


def _config(server: RemoteServer) -> RemoteServerConfig:
    return RemoteServerConfig(
        protocol=server.protocol,
        host=server.host,
        port=server.port,
        username=server.username,
        base_path=server.base_path,
        allowlist=list(server.allowlist or []),
    )


def _targets(server: RemoteServer, rule: dict[str, Any]) -> list[str]:
    allowlist = list(server.allowlist or [])
    if not allowlist:
        raise DomainError(
            "REMOTE_ALLOWLIST_EMPTY",
            "El servidor no tiene rutas autorizadas",
            403,
        )
    raw_targets = rule.get("rutasPermitidas") or allowlist
    return [validate_remote_path(path, allowlist) for path in raw_targets]


def _execution_payload(
    execution: RemoteCleanupExecution, server_name: str = ""
) -> dict[str, Any]:
    summary = execution.summary or {}
    return {
        "id": str(execution.id),
        "tipo": execution.kind,
        "serverId": str(execution.server_id),
        "serverName": server_name or summary.get("serverName", ""),
        "targets": execution.targets,
        "actor": summary.get("actor", ""),
        "startedAt": execution.started_at.isoformat(),
        "finishedAt": (
            execution.finished_at.isoformat() if execution.finished_at else None
        ),
        "encontrados": summary.get("encontrados", 0),
        "elegibles": summary.get("elegibles", 0),
        "movidos": summary.get("movidos", 0),
        "omitidos": summary.get("omitidos", 0),
        "fallidos": summary.get("fallidos", 0),
        "espacioBytes": summary.get("espacioBytes", 0),
        "estado": execution.status,
        "cuarentena": summary.get("cuarentena", True),
        "errores": summary.get("errores", []),
        "truncated": summary.get("truncated", False),
    }


def _quarantine_payload(item: RemoteQuarantineItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "execId": str(item.execution_id) if item.execution_id else "",
        "serverId": str(item.server_id),
        "name": item.name,
        "originalPath": item.original_path,
        "quarantinePath": item.quarantine_path,
        "sizeBytes": item.size_bytes,
        "movedAt": item.created_at.isoformat(),
        "actor": str(item.moved_by) if item.moved_by else "",
        "retentionDays": item.retention_days,
    }


class RemoteCleanupService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = RemoteRepository(db)

    async def list_servers(self, tenant_id: str) -> list[dict[str, Any]]:
        return [
            _server_payload(server)
            for server in await self.repo.list_servers(tenant_id)
        ]

    async def create_server(
        self, tenant_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        allowlist = [validate_remote_path(path, [path]) for path in data["allowlist"]]
        if not allowlist:
            raise DomainError(
                "REMOTE_ALLOWLIST_EMPTY", "La allowlist no puede estar vacía", 422
            )
        server = RemoteServer(
            tenant_id=tenant_uuid(tenant_id),
            name=data["name"].strip(),
            protocol=data["protocol"],
            host=data["host"].strip(),
            port=data["port"],
            username=data["username"].strip(),
            base_path=validate_remote_path(data["rutaBase"], allowlist),
            allowlist=allowlist,
        )
        self.db.add(server)
        await self.db.flush()
        return _server_payload(server)

    async def update_server(
        self, tenant_id: str, server_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        server = await self.repo.get_server(tenant_id, server_id)
        allowlist = [
            validate_remote_path(path, [path]) for path in data["allowlist"]
        ]
        if not allowlist:
            raise DomainError(
                "REMOTE_ALLOWLIST_EMPTY", "La allowlist no puede estar vacía", 422
            )
        server.name = data["name"].strip()
        server.protocol = data["protocol"]
        server.host = data["host"].strip()
        server.port = data["port"]
        server.username = data["username"].strip()
        server.base_path = validate_remote_path(data["rutaBase"], allowlist)
        server.allowlist = allowlist
        await self.db.flush()
        return _server_payload(server)

    async def delete_server(self, tenant_id: str, server_id: str) -> None:
        server = await self.repo.get_server(tenant_id, server_id)
        await self.db.delete(server)

    async def _verify_host_key(
        self, tenant_id: str, server: RemoteServer
    ) -> None:
        if server.protocol != "sftp":
            return
        algorithm, fingerprint = await asyncio.to_thread(
            probe_ssh_host_key, server.host, server.port
        )
        known = await self.repo.get_host_key(tenant_id, server.host, server.port)
        if known and (
            known.algorithm != algorithm or known.fingerprint != fingerprint
        ):
            raise ConflictError(
                "La clave SSH del servidor cambió. Un administrador debe revisarla.",
                code="REMOTE_HOST_KEY_CHANGED",
            )
        if not known:
            self.db.add(
                SshHostKey(
                    tenant_id=tenant_uuid(tenant_id),
                    host=server.host,
                    port=server.port,
                    algorithm=algorithm,
                    fingerprint=fingerprint,
                )
            )
            await self.db.flush()

    async def list_directory(
        self,
        tenant_id: str,
        server_id: str,
        credentials: RemoteCredentials,
        path: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        server = await self.repo.get_server(tenant_id, server_id)
        await self._verify_host_key(tenant_id, server)
        requested = path or server.allowlist[0]
        safe_path = validate_remote_path(requested, server.allowlist)

        def operation() -> list[dict]:
            client = open_remote_client(_config(server), credentials)
            try:
                return client.list_one(safe_path)
            finally:
                client.close()

        entries = await asyncio.to_thread(operation)
        entries.sort(key=lambda item: (not item["isDir"], item["name"].lower()))
        start = (page - 1) * page_size
        return {
            "path": safe_path,
            "entries": entries[start : start + page_size],
            "total": len(entries),
            "page": page,
            "pageSize": page_size,
        }

    async def simulate(
        self,
        tenant_id: str,
        server_id: str,
        credentials: RemoteCredentials,
        rule: dict[str, Any],
    ) -> dict[str, Any]:
        server = await self.repo.get_server(tenant_id, server_id)
        await self._verify_host_key(tenant_id, server)
        targets = _targets(server, rule)

        def operation() -> tuple[list[dict], bool]:
            client = open_remote_client(_config(server), credentials)
            try:
                return client.collect_tree(targets, server.allowlist)
            finally:
                client.close()

        files, truncated = await asyncio.to_thread(operation)
        report = select_candidates(files, rule, time.time())
        report.update(
            {
                "simulacion": True,
                "truncated": truncated,
                "targets": targets,
            }
        )
        if truncated:
            report["warnings"].append(
                "El recorrido llegó al límite de 50000 elementos."
            )
        return report

    async def execute(
        self,
        tenant_id: str,
        user_id: str,
        actor: str,
        server_id: str,
        credentials: RemoteCredentials,
        rule: dict[str, Any],
        confirmar: bool,
        conteo_esperado: int | None,
    ) -> dict[str, Any]:
        if not confirmar or conteo_esperado is None:
            raise DomainError(
                "SIMULATION_REQUIRED",
                "Debe simular y confirmar el conteo antes de ejecutar",
                409,
            )
        server = await self.repo.get_server(tenant_id, server_id)
        await self._verify_host_key(tenant_id, server)
        targets = _targets(server, rule)
        execution = RemoteCleanupExecution(
            tenant_id=tenant_uuid(tenant_id),
            server_id=server.id,
            user_id=uuid.UUID(user_id),
            kind="manual",
            status="running",
            targets=targets,
            summary={},
        )
        self.db.add(execution)
        await self.db.flush()
        retention = int((rule.get("cuarentena") or {}).get("retencionDias", 15))

        def operation() -> tuple[dict[str, Any], list[tuple[dict, str]], list[dict]]:
            client = open_remote_client(_config(server), credentials)
            moved: list[tuple[dict, str]] = []
            failed: list[dict] = []
            try:
                files, truncated = client.collect_tree(targets, server.allowlist)
                report = select_candidates(files, rule, time.time())
                report["truncated"] = truncated
                if report["elegiblesCount"] != conteo_esperado:
                    raise ConflictError(
                        "El conteo cambió. Vuelva a simular antes de ejecutar.",
                        code="SIMULATION_STALE",
                    )
                for entry in report["elegibles"]:
                    destination = quarantine_path(
                        server.base_path, str(execution.id), entry["path"]
                    )
                    try:
                        client.move(entry["path"], destination)
                        moved.append((entry, destination))
                    except Exception as exc:
                        failed.append(
                            {"path": entry["path"], "error": str(exc)[:512]}
                        )
                return report, moved, failed
            finally:
                client.close()

        report, moved, failed = await asyncio.to_thread(operation)
        for entry, destination in moved:
            self.db.add(
                RemoteQuarantineItem(
                    tenant_id=tenant_uuid(tenant_id),
                    execution_id=execution.id,
                    server_id=server.id,
                    name=entry.get("name", ""),
                    original_path=entry["path"],
                    quarantine_path=destination,
                    size_bytes=int(entry.get("sizeBytes", 0) or 0),
                    moved_by=uuid.UUID(user_id),
                    retention_days=retention,
                )
            )
        summary = {
            "serverName": server.name,
            "actor": actor,
            "encontrados": report["encontrados"],
            "elegibles": report["elegiblesCount"],
            "movidos": len(moved),
            "omitidos": report["excluidosCount"],
            "fallidos": len(failed),
            "espacioBytes": sum(
                int(entry.get("sizeBytes", 0) or 0) for entry, _ in moved
            ),
            "errores": failed[:50],
            "cuarentena": True,
            "truncated": report.get("truncated", False),
        }
        execution.summary = summary
        execution.status = "completado" if not failed else "parcial"
        execution.finished_at = datetime.now(timezone.utc)
        await self.db.flush()
        return _execution_payload(execution, server.name)

    async def history(self, tenant_id: str) -> list[dict[str, Any]]:
        return [
            _execution_payload(item)
            for item in await self.repo.list_executions(tenant_id)
        ]

    async def history_detail(
        self, tenant_id: str, execution_id: str
    ) -> dict[str, Any]:
        return _execution_payload(
            await self.repo.get_execution(tenant_id, execution_id)
        )

    async def quarantine(self, tenant_id: str) -> list[dict[str, Any]]:
        return [
            _quarantine_payload(item)
            for item in await self.repo.list_quarantine(tenant_id)
        ]

    async def restore(
        self,
        tenant_id: str,
        item_id: str,
        credentials: RemoteCredentials,
    ) -> dict[str, str]:
        item = await self.repo.get_quarantine(tenant_id, item_id)
        server = await self.repo.get_server(tenant_id, str(item.server_id))
        validate_remote_path(item.original_path, server.allowlist)
        await self._verify_host_key(tenant_id, server)

        def operation() -> None:
            client = open_remote_client(_config(server), credentials)
            try:
                client.move(item.quarantine_path, item.original_path)
            finally:
                client.close()

        await asyncio.to_thread(operation)
        item.restored_at = datetime.now(timezone.utc)
        return {"restored": item.original_path}

    async def purge(
        self,
        tenant_id: str,
        server_id: str,
        credentials: RemoteCredentials,
        ids: list[str],
        purge_expired: bool,
    ) -> dict[str, Any]:
        server = await self.repo.get_server(tenant_id, server_id)
        await self._verify_host_key(tenant_id, server)
        all_items = await self.repo.list_quarantine(tenant_id)
        selected = [
            item
            for item in all_items
            if item.server_id == server.id
            and (
                str(item.id) in ids
                or (
                    purge_expired
                    and item.created_at
                    + timedelta(days=item.retention_days)
                    <= datetime.now(timezone.utc)
                )
            )
        ]

        def operation() -> tuple[list[RemoteQuarantineItem], list[dict]]:
            client = open_remote_client(_config(server), credentials)
            deleted_items: list[RemoteQuarantineItem] = []
            failed: list[dict] = []
            try:
                for item in selected:
                    try:
                        client.remove(item.quarantine_path)
                        deleted_items.append(item)
                    except Exception as exc:
                        failed.append({"id": str(item.id), "error": str(exc)[:512]})
                return deleted_items, failed
            finally:
                client.close()

        deleted_items, failed = await asyncio.to_thread(operation)
        now = datetime.now(timezone.utc)
        for item in deleted_items:
            item.purged_at = now
        return {"deleted": len(deleted_items), "failed": failed}

    async def list_host_keys(self, tenant_id: str) -> list[dict[str, Any]]:
        return [
            {
                "host": item.host,
                "port": item.port,
                "algorithm": item.algorithm,
                "fingerprint": item.fingerprint,
                "verifiedAt": item.verified_at.isoformat(),
            }
            for item in await self.repo.list_host_keys(tenant_id)
        ]

    async def forget_host_key(
        self, tenant_id: str, host: str, port: int
    ) -> dict[str, Any]:
        result = await self.db.execute(
            delete(SshHostKey).where(
                SshHostKey.tenant_id == tenant_uuid(tenant_id),
                SshHostKey.host == host,
                SshHostKey.port == port,
            )
        )
        return {"forgotten": bool(result.rowcount), "host": f"{host}:{port}"}

    async def start_structural_job(
        self,
        tenant_id: str,
        user_id: str,
        server_id: str,
        credentials: RemoteCredentials,
        rule: dict[str, Any],
        kind: str,
        mode: str,
        confirmar: bool,
        conteo_esperado: int | None,
        max_properties: int,
    ) -> str:
        if kind == "execute" and (not confirmar or conteo_esperado is None):
            raise DomainError(
                "SIMULATION_REQUIRED",
                "Debe simular y confirmar el conteo antes de ejecutar",
                409,
            )
        server = await self.repo.get_server(tenant_id, server_id)
        await self._verify_host_key(tenant_id, server)
        job = BackgroundJob(
            tenant_id=tenant_uuid(tenant_id),
            kind=kind,
            status="running",
            phase="queued",
            resource_id=server.id,
        )
        self.db.add(job)
        await self.db.commit()
        asyncio.create_task(
            self._run_structural_job(
                tenant_id,
                user_id,
                str(server.id),
                str(job.id),
                credentials,
                rule,
                kind,
                mode,
                conteo_esperado,
                max_properties,
            )
        )
        return str(job.id)

    @staticmethod
    async def _run_structural_job(
        tenant_id: str,
        user_id: str,
        server_id: str,
        job_id: str,
        credentials: RemoteCredentials,
        rule: dict[str, Any],
        kind: str,
        mode: str,
        conteo_esperado: int | None,
        max_properties: int,
    ) -> None:
        async with AsyncSessionLocal() as db:
            service = RemoteCleanupService(db)
            try:
                job = await service.repo.get_job(tenant_id, job_id)
                server = await service.repo.get_server(tenant_id, server_id)
                job.phase = "discovering"
                root = validate_remote_path(
                    rule.get("raiz") or server.base_path, server.allowlist
                )

                def collect() -> tuple[list[dict], bool]:
                    client = open_remote_client(_config(server), credentials)
                    try:
                        return client.collect_tree([root], server.allowlist)
                    finally:
                        client.close()

                entries, truncated = await asyncio.to_thread(collect)
                root_parts = [part for part in root.split("/") if part]
                properties: list[str] = []
                for entry in entries:
                    relative = [
                        part for part in entry["path"].split("/") if part
                    ][len(root_parts) :]
                    if relative and relative[0] not in properties:
                        properties.append(relative[0])
                if max_properties > 0:
                    properties = properties[:max_properties]
                allowed_properties = set(properties)
                container = str(rule.get("carpetaContenedora", "core")).lower()
                empty_folders = {
                    str(value).lower()
                    for value in rule.get("vaciarCarpetas", [])
                }
                target_files = {
                    str(value).lower()
                    for value in rule.get("borrarArchivos", [])
                }
                candidates: list[dict] = []
                for entry in entries:
                    if entry.get("isDir"):
                        continue
                    relative = [
                        part for part in entry["path"].split("/") if part
                    ][len(root_parts) :]
                    if len(relative) < 3 or relative[0] not in allowed_properties:
                        continue
                    lowered = [part.lower() for part in relative]
                    direct_file = (
                        len(lowered) == 3
                        and lowered[1] == container
                        and lowered[2] in target_files
                    )
                    inside_target = (
                        len(lowered) >= 4
                        and lowered[1] == container
                        and lowered[2] in empty_folders
                    )
                    if direct_file or inside_target:
                        enriched = dict(entry)
                        enriched["propiedad"] = relative[0]
                        candidates.append(enriched)
                report = select_structural(candidates, rule, rule.get("limites"))
                report.update(
                    {
                        "simulacion": kind == "simulate",
                        "propiedadesTotales": len(properties),
                        "truncated": truncated,
                        "raiz": root,
                    }
                )
                job.total_units = len(properties)
                job.processed_units = len(properties)
                job.found_count = report["encontrados"]
                if job.cancel_requested:
                    job.status = "cancelado"
                    job.phase = "cancelled"
                elif kind == "execute":
                    if report["elegiblesCount"] != conteo_esperado:
                        raise ConflictError(
                            "El conteo cambió. Vuelva a simular.",
                            code="SIMULATION_STALE",
                        )
                    execution_record = RemoteCleanupExecution(
                        tenant_id=tenant_uuid(tenant_id),
                        server_id=server.id,
                        user_id=uuid.UUID(user_id),
                        kind="structural",
                        status="running",
                        targets=[root],
                        summary={},
                    )
                    db.add(execution_record)
                    await db.flush()

                    def execute() -> tuple[list[tuple[dict, str | None]], list[dict]]:
                        client = open_remote_client(_config(server), credentials)
                        succeeded: list[tuple[dict, str | None]] = []
                        failed: list[dict] = []
                        try:
                            for entry in report["elegibles"]:
                                try:
                                    destination: str | None = None
                                    if mode == "directo":
                                        client.remove(entry["path"])
                                    else:
                                        destination = quarantine_path(
                                            server.base_path,
                                            str(execution_record.id),
                                            entry["path"],
                                        )
                                        client.move(entry["path"], destination)
                                    succeeded.append((entry, destination))
                                except Exception as exc:
                                    failed.append(
                                        {
                                            "path": entry["path"],
                                            "error": str(exc)[:512],
                                        }
                                    )
                            return succeeded, failed
                        finally:
                            client.close()

                    succeeded, failed = await asyncio.to_thread(execute)
                    if mode != "directo":
                        for entry, destination in succeeded:
                            db.add(
                                RemoteQuarantineItem(
                                    tenant_id=tenant_uuid(tenant_id),
                                    execution_id=execution_record.id,
                                    server_id=server.id,
                                    name=entry.get("name", ""),
                                    original_path=entry["path"],
                                    quarantine_path=destination or "",
                                    size_bytes=int(entry.get("sizeBytes", 0) or 0),
                                    moved_by=uuid.UUID(user_id),
                                    retention_days=15,
                                )
                            )
                    moved = len(succeeded)
                    report["movidos"] = moved
                    report["fallidos"] = len(failed)
                    report["errores"] = failed[:50]
                    execution_record.status = (
                        "completado" if not failed else "parcial"
                    )
                    execution_record.summary = {
                        "serverName": server.name,
                        "actor": str(user_id),
                        "encontrados": report["encontrados"],
                        "elegibles": report["elegiblesCount"],
                        "movidos": moved,
                        "omitidos": report["excluidosCount"],
                        "fallidos": len(failed),
                        "espacioBytes": sum(
                            int(entry.get("sizeBytes", 0) or 0)
                            for entry, _ in succeeded
                        ),
                        "errores": failed[:50],
                        "cuarentena": mode != "directo",
                        "truncated": truncated,
                    }
                    execution_record.finished_at = datetime.now(timezone.utc)
                    job.status = "completado" if not failed else "parcial"
                    job.phase = "completed"
                else:
                    job.status = "completado"
                    job.phase = "completed"
                job.result = report
                job.finished_at = datetime.now(timezone.utc)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                try:
                    job = await RemoteRepository(db).get_job(tenant_id, job_id)
                    job.status = "error"
                    job.phase = "failed"
                    job.error = str(exc)[:1000]
                    job.finished_at = datetime.now(timezone.utc)
                    await db.commit()
                except Exception:
                    await db.rollback()

    async def job(self, tenant_id: str, job_id: str) -> dict[str, Any]:
        job = await self.repo.get_job(tenant_id, job_id)
        return {
            "id": str(job.id),
            "kind": job.kind,
            "status": job.status,
            "fase": job.phase,
            "propiedadesTotales": job.total_units,
            "propiedadesProcesadas": job.processed_units,
            "encontrados": job.found_count,
            "result": job.result,
            "error": job.error,
        }

    async def cancel_job(self, tenant_id: str, job_id: str) -> dict[str, Any]:
        job = await self.repo.get_job(tenant_id, job_id)
        job.cancel_requested = True
        if job.status == "running":
            job.phase = "cancellation_requested"
        return {"cancelRequested": True, "jobId": str(job.id)}
