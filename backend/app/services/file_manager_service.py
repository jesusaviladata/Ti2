from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError, NotFoundError
from app.models.operations import SshHostKey
from app.repositories.cleanup_repository import tenant_uuid
from app.repositories.remote_repository import RemoteRepository
from app.services.remote_transport import (
    RemoteCredentials,
    RemoteServerConfig,
    open_remote_client,
    probe_ssh_host_key,
    validate_remote_path,
)


def _local_roots() -> list[Path]:
    value = os.getenv("FM_ALLOWED_ROOTS", "")
    roots: list[Path] = []
    for raw in value.split(";"):
        if raw.strip():
            roots.append(Path(raw.strip()).resolve())
    return roots


def _safe_local_path(raw_path: str, *, allow_root: bool = True) -> Path:
    roots = _local_roots()
    if not roots:
        raise DomainError(
            "FM_LOCAL_DISABLED",
            "El administrador de archivos local requiere FM_ALLOWED_ROOTS",
            503,
        )
    path = Path(raw_path).resolve()
    for root in roots:
        if path == root:
            if allow_root:
                return path
            raise DomainError(
                "FM_ROOT_PROTECTED", "No se puede eliminar una raíz autorizada", 403
            )
        if path.is_relative_to(root):
            return path
    raise DomainError(
        "FM_PATH_NOT_ALLOWED", "La ruta está fuera de FM_ALLOWED_ROOTS", 403
    )


def _remote_config(connection: dict[str, Any]) -> RemoteServerConfig:
    protocol = connection["protocol"]
    return RemoteServerConfig(
        protocol=protocol,
        host=connection["host"],
        port=connection.get("port") or (22 if protocol == "sftp" else 21),
        username=connection["username"],
        base_path="/",
        allowlist=["/"],
    )


def _remote_credentials(connection: dict[str, Any]) -> RemoteCredentials:
    return RemoteCredentials(
        password=connection.get("password", ""),
        private_key=connection.get("privateKey", ""),
        passphrase=connection.get("passphrase", ""),
    )


class FileManagerService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = RemoteRepository(db)

    async def _verify_remote_key(
        self, tenant_id: str, connection: dict[str, Any]
    ) -> None:
        if connection["protocol"] != "sftp":
            return
        config = _remote_config(connection)
        algorithm, fingerprint = await asyncio.to_thread(
            probe_ssh_host_key, config.host, config.port
        )
        known = await self.repo.get_host_key(tenant_id, config.host, config.port)
        if known and (
            known.algorithm != algorithm or known.fingerprint != fingerprint
        ):
            raise DomainError(
                "REMOTE_HOST_KEY_CHANGED",
                "La clave SSH cambió; debe revisarla un administrador",
                409,
            )
        if not known:
            self.db.add(
                SshHostKey(
                    tenant_id=tenant_uuid(tenant_id),
                    host=config.host,
                    port=config.port,
                    algorithm=algorithm,
                    fingerprint=fingerprint,
                )
            )
            await self.db.flush()

    async def test(
        self, tenant_id: str, connection: dict[str, Any] | None
    ) -> dict[str, Any]:
        try:
            await self.list(tenant_id, connection, "/" if connection else str(_local_roots()[0]))
            return {"connected": True}
        except Exception as exc:
            return {"connected": False, "error": str(exc)[:512]}

    async def list(
        self,
        tenant_id: str,
        connection: dict[str, Any] | None,
        raw_path: str,
    ) -> dict[str, Any]:
        if connection is None:
            path = _safe_local_path(raw_path)
            if not path.exists():
                raise NotFoundError("Ruta")
            if not path.is_dir():
                raise DomainError("FM_NOT_DIRECTORY", "La ruta no es una carpeta", 422)

            def local_operation() -> list[dict[str, Any]]:
                entries: list[dict[str, Any]] = []
                for item in path.iterdir():
                    try:
                        stat = item.stat()
                        entries.append(
                            {
                                "name": item.name,
                                "size": stat.st_size if item.is_file() else 0,
                                "modified": stat.st_mtime,
                                "isDir": item.is_dir(),
                                "permissions": None,
                            }
                        )
                    except (OSError, PermissionError):
                        continue
                entries.sort(key=lambda item: (not item["isDir"], item["name"].lower()))
                return entries

            return {
                "entries": await asyncio.to_thread(local_operation),
                "path": str(path),
            }

        await self._verify_remote_key(tenant_id, connection)
        path = validate_remote_path(raw_path, ["/"])

        def remote_operation() -> list[dict[str, Any]]:
            client = open_remote_client(
                _remote_config(connection), _remote_credentials(connection)
            )
            try:
                raw_entries = client.list_one(path)
                result = [
                    {
                        "name": item["name"],
                        "size": item["sizeBytes"],
                        "modified": item["modified"],
                        "isDir": item["isDir"],
                        "permissions": item.get("permissions"),
                    }
                    for item in raw_entries
                ]
                result.sort(
                    key=lambda item: (not item["isDir"], item["name"].lower())
                )
                return result
            finally:
                client.close()

        return {"entries": await asyncio.to_thread(remote_operation), "path": path}

    async def mkdir(
        self,
        tenant_id: str,
        connection: dict[str, Any] | None,
        raw_path: str,
    ) -> dict[str, str]:
        if connection is None:
            path = _safe_local_path(raw_path)
            await asyncio.to_thread(path.mkdir, parents=True, exist_ok=True)
            return {"created": str(path)}
        await self._verify_remote_key(tenant_id, connection)
        path = validate_remote_path(raw_path, ["/"])

        def operation() -> None:
            client = open_remote_client(
                _remote_config(connection), _remote_credentials(connection)
            )
            try:
                client.mkdir(path)
            finally:
                client.close()

        await asyncio.to_thread(operation)
        return {"created": path}

    async def delete(
        self,
        tenant_id: str,
        connection: dict[str, Any] | None,
        raw_path: str,
        contents_only: bool,
    ) -> dict[str, int]:
        if connection is None:
            path = _safe_local_path(raw_path, allow_root=contents_only)
            if not path.exists():
                raise NotFoundError("Ruta")

            def local_operation() -> int:
                if contents_only:
                    if not path.is_dir():
                        raise DomainError(
                            "FM_NOT_DIRECTORY", "La ruta no es una carpeta", 422
                        )
                    children = list(path.iterdir())
                    for child in children:
                        if child.is_dir():
                            shutil.rmtree(child)
                        else:
                            child.unlink()
                    return len(children)
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                return 1

            return {"deleted": await asyncio.to_thread(local_operation)}

        await self._verify_remote_key(tenant_id, connection)
        path = validate_remote_path(raw_path, ["/"])
        if path == "/" and not contents_only:
            raise DomainError("FM_ROOT_PROTECTED", "No se puede eliminar /", 403)

        def remote_operation() -> int:
            client = open_remote_client(
                _remote_config(connection), _remote_credentials(connection)
            )

            def remove_tree(directory: str, keep_directory: bool = False) -> int:
                count = 0
                for item in client.list_one(directory):
                    if item["isDir"] and not item.get("isLink"):
                        count += remove_tree(item["path"])
                    else:
                        client.remove(item["path"])
                        count += 1
                if not keep_directory:
                    client.rmdir(directory)
                return count

            try:
                if contents_only:
                    return remove_tree(path, keep_directory=True)
                try:
                    client.remove(path)
                    return 1
                except Exception:
                    return max(1, remove_tree(path))
            finally:
                client.close()

        return {"deleted": await asyncio.to_thread(remote_operation)}
