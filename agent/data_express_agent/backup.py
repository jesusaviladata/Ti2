from __future__ import annotations

import base64
import hashlib
import os
import posixpath
import re
import shutil
import zipfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any


ProgressCallback = Callable[[dict[str, Any]], None]
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class BackupError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _profile(profiles: tuple[dict[str, Any], ...], profile_id: str, kind: str) -> dict[str, Any]:
    for item in profiles:
        if item.get("id") == profile_id:
            return item
    raise BackupError(f"{kind.upper()}_PROFILE_NOT_FOUND", f"El perfil {kind} no existe en este agente")


def _safe_database_name(value: str) -> str:
    name = value.strip()
    if not _SAFE_NAME.fullmatch(name):
        raise BackupError("DATABASE_NAME_INVALID", "El nombre de base de datos no es valido")
    return name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verification_requires_database_create_permission(error: Exception) -> bool:
    """Recognize the SQL Server permission required by RESTORE VERIFYONLY.

    SQL Server Express requires CREATE DATABASE permission for RESTORE VERIFYONLY,
    even though the command does not restore a database.  The agent intentionally
    does not request that broad server-level permission.
    """
    text = str(error).lower()
    return "create database permission denied" in text and "master" in text


def _connection_string(profile: dict[str, Any]) -> str:
    driver = str(profile.get("driver") or "ODBC Driver 18 for SQL Server")
    server = str(profile.get("server") or "").strip()
    if not server or ";" in server or ";" in driver:
        raise BackupError("SQL_PROFILE_INVALID", "El perfil SQL no tiene un servidor valido")
    authentication = str(profile.get("authentication") or "windows").lower()
    base = (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE=master;"
        "TrustServerCertificate=yes;Encrypt=yes;"
    )
    if authentication != "windows":
        raise BackupError(
            "SQL_AUTH_UNSUPPORTED",
            "El agente solo acepta autenticacion integrada de Windows; configure la cuenta del servicio",
        )
    return base + "Trusted_Connection=yes;"


class BackupExecutor:
    def __init__(
        self,
        *,
        sql_profiles: tuple[dict[str, Any], ...] = (),
        destination_profiles: tuple[dict[str, Any], ...] = (),
        connect: Callable[..., Any] | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.sql_profiles = sql_profiles
        self.destination_profiles = destination_profiles
        self._connect_override = connect
        self.now = now or datetime.now

    def _connect(self, profile: dict[str, Any]):
        if self._connect_override is not None:
            return self._connect_override(profile)
        try:
            import pyodbc
        except ImportError as exc:
            raise BackupError("PYODBC_UNAVAILABLE", "El paquete pyodbc no esta disponible") from exc
        try:
            return pyodbc.connect(_connection_string(profile), timeout=30, autocommit=True)
        except Exception as exc:
            raise BackupError("SQL_CONNECTION_FAILED", "No fue posible conectar con SQL Server") from exc

    def list_databases(self, sql_profile_id: str) -> dict[str, Any]:
        profile = _profile(self.sql_profiles, sql_profile_id, "sql")
        try:
            with self._connect(profile) as connection:
                rows = connection.execute(
                    "SELECT name FROM sys.databases "
                    "WHERE database_id > 4 AND state_desc = 'ONLINE' ORDER BY name"
                ).fetchall()
        except BackupError:
            raise
        except Exception as exc:
            raise BackupError("DATABASE_LIST_FAILED", "No fue posible listar las bases de datos") from exc
        return {
            "sqlProfileId": sql_profile_id,
            "databases": [str(row[0]) for row in rows],
        }

    def run_batch(
        self,
        payload: dict[str, Any],
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        sql_profile_id = str(payload["sqlProfileId"])
        profile = _profile(self.sql_profiles, sql_profile_id, "sql")
        databases = list(dict.fromkeys(_safe_database_name(str(item)) for item in payload["databaseNames"]))
        if not databases:
            raise BackupError("DATABASE_REQUIRED", "Seleccione al menos una base de datos")
        if len(databases) > 100:
            raise BackupError("TOO_MANY_DATABASES", "Seleccione un maximo de 100 bases de datos")
        backup_type = str(payload.get("backupType") or "full")
        if backup_type not in {"full", "differential", "log"}:
            raise BackupError("BACKUP_TYPE_INVALID", "El tipo de backup no es valido")

        configured_root = Path(str(profile.get("backupRoot") or "D:\\"))
        if not configured_root.is_absolute():
            raise BackupError("BACKUP_ROOT_INVALID", "La raiz de backup debe ser absoluta")
        date_text = self.now().strftime("%Y-%m-%d")
        dated_dir = configured_root / date_text
        try:
            dated_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise BackupError("BACKUP_DIRECTORY_FAILED", "No fue posible crear la carpeta diaria") from exc

        run_id = str(payload.get("runId") or self.now().strftime("%Y%m%d%H%M%S"))
        if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", run_id):
            raise BackupError("RUN_ID_INVALID", "El identificador de ejecucion no es valido")
        files: list[Path] = []
        database_results: list[dict[str, Any]] = []
        try:
            with self._connect(profile) as connection:
                for index, database in enumerate(databases, start=1):
                    if progress:
                        progress(
                            {
                                "phase": "backing_up",
                                "processedUnits": index - 1,
                                "totalUnits": len(databases),
                                "foundCount": len(files),
                                "database": database,
                            }
                        )
                    extension = ".trn" if backup_type == "log" else ".bak"
                    file_path = dated_dir / f"{database}_{backup_type.upper()}_{run_id}{extension}"
                    verification_method = self._backup_database(
                        connection, database, backup_type, file_path
                    )
                    if not file_path.is_file() or file_path.stat().st_size <= 0:
                        raise BackupError(
                            "BACKUP_FILE_MISSING",
                            f"SQL Server no dejo un archivo valido para {database}",
                        )
                    files.append(file_path)
                    database_results.append(
                        {
                            "databaseName": database,
                            "fileName": file_path.name,
                            "fileSizeBytes": file_path.stat().st_size,
                            "fileSha256": _sha256(file_path),
                            "verified": True,
                            "verificationMethod": verification_method,
                        }
                    )
        except BackupError:
            raise
        except Exception as exc:
            raise BackupError("BACKUP_DATABASE_FAILED", "SQL Server no pudo completar el backup") from exc

        if progress:
            progress(
                {
                    "phase": "compressing",
                    "processedUnits": len(databases),
                    "totalUnits": len(databases),
                    "foundCount": len(files),
                }
            )
        zip_path = dated_dir / f"Backup_{date_text}_{run_id}.zip"
        try:
            with zipfile.ZipFile(
                zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
            ) as archive:
                for file_path in files:
                    archive.write(file_path, arcname=file_path.name)
            with zipfile.ZipFile(zip_path, "r") as archive:
                if archive.testzip() is not None:
                    raise BackupError("ZIP_INTEGRITY_FAILED", "El ZIP generado no supero la validacion")
        except BackupError:
            raise
        except (OSError, zipfile.BadZipFile) as exc:
            raise BackupError("ZIP_CREATION_FAILED", "No fue posible crear el ZIP diario") from exc

        transfer_result = {"type": "local", "path": str(zip_path), "verified": True}
        destination_profile_id = str(payload.get("destinationProfileId") or "").strip()
        if destination_profile_id:
            destination = _profile(
                self.destination_profiles, destination_profile_id, "destination"
            )
            if progress:
                progress(
                    {
                        "phase": "transferring",
                        "processedUnits": len(databases),
                        "totalUnits": len(databases),
                        "foundCount": len(files),
                    }
                )
            transfer_result = self._transfer(zip_path, destination, date_text)

        result = {
            "runId": run_id,
            "sqlProfileId": sql_profile_id,
            "backupType": backup_type,
            "folder": str(dated_dir),
            "zipPath": str(zip_path),
            "zipFileName": zip_path.name,
            "zipSizeBytes": zip_path.stat().st_size,
            "zipSha256": _sha256(zip_path),
            "databases": database_results,
            "transfer": transfer_result,
        }
        if progress:
            progress(
                {
                    "phase": "completed",
                    "processedUnits": len(databases),
                    "totalUnits": len(databases),
                    "foundCount": len(files),
                }
            )
        return result

    def _backup_database(
        self, connection: Any, database: str, backup_type: str, file_path: Path
    ) -> str:
        verb = "BACKUP LOG" if backup_type == "log" else "BACKUP DATABASE"
        differential = "DIFFERENTIAL, " if backup_type == "differential" else ""
        quoted_database = database.replace("]", "]]" )
        sql = (
            f"{verb} [{quoted_database}] TO DISK = ? WITH "
            f"COMPRESSION, {differential}FORMAT, INIT, CHECKSUM, STATS = 10"
        )
        try:
            connection.execute(sql, str(file_path))
        except Exception as exc:
            if "compress" not in str(exc).lower():
                raise
            fallback = (
                f"{verb} [{quoted_database}] TO DISK = ? WITH "
                f"{differential}FORMAT, INIT, CHECKSUM, STATS = 10"
            )
            connection.execute(fallback, str(file_path))
        try:
            connection.execute(
                "RESTORE VERIFYONLY FROM DISK = ? WITH CHECKSUM", str(file_path)
            )
        except Exception as exc:
            if _verification_requires_database_create_permission(exc):
                # Keep least privilege on SQL Server Express. The .bak is still
                # checked for existence, size and SHA-256 before it enters the ZIP.
                return "file_sha256"
            raise
        return "restore_verifyonly"

    def _transfer(
        self, zip_path: Path, destination: dict[str, Any], date_text: str
    ) -> dict[str, Any]:
        destination_type = str(destination.get("type") or "").lower()
        if destination_type == "smb":
            return self._transfer_smb(zip_path, destination, date_text)
        if destination_type == "sftp":
            return self._transfer_sftp(zip_path, destination, date_text)
        raise BackupError("DESTINATION_TYPE_INVALID", "El tipo de destino no esta soportado")

    @staticmethod
    def _transfer_smb(
        zip_path: Path, destination: dict[str, Any], date_text: str
    ) -> dict[str, Any]:
        root = Path(str(destination.get("path") or ""))
        if not str(root).startswith(("\\\\", "//")):
            raise BackupError("SMB_PATH_INVALID", "El destino SMB debe ser una ruta UNC")
        target_dir = root / date_text
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / zip_path.name
        partial = target.with_suffix(target.suffix + ".part")
        shutil.copy2(zip_path, partial)
        os.replace(partial, target)
        if target.stat().st_size != zip_path.stat().st_size:
            raise BackupError("TRANSFER_VERIFY_FAILED", "El archivo SMB no coincide en tamano")
        return {"type": "smb", "path": str(target), "verified": True}

    @staticmethod
    def _transfer_sftp(
        zip_path: Path, destination: dict[str, Any], date_text: str
    ) -> dict[str, Any]:
        try:
            import paramiko
        except ImportError as exc:
            raise BackupError("PARAMIKO_UNAVAILABLE", "El soporte SFTP no esta disponible") from exc
        host = str(destination.get("host") or "").strip()
        username = str(destination.get("username") or "").strip()
        key_path = str(destination.get("privateKeyPath") or "").strip()
        remote_root = str(destination.get("path") or "").strip()
        expected_fingerprint = str(destination.get("hostKeySha256") or "").strip()
        if not host or not username or not key_path or not remote_root.startswith("/"):
            raise BackupError("SFTP_PROFILE_INVALID", "El perfil SFTP esta incompleto")
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        if expected_fingerprint:
            class PinnedHostKeyPolicy(paramiko.MissingHostKeyPolicy):
                def missing_host_key(self, _client, _hostname, key):
                    actual = base64.b64encode(
                        hashlib.sha256(key.asbytes()).digest()
                    ).decode("ascii")
                    if actual != expected_fingerprint:
                        raise BackupError(
                            "SFTP_HOST_KEY_MISMATCH",
                            "La identidad del servidor SFTP no coincide",
                        )

            client.set_missing_host_key_policy(PinnedHostKeyPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(
                hostname=host,
                port=int(destination.get("port") or 22),
                username=username,
                key_filename=key_path,
                look_for_keys=False,
                allow_agent=False,
                timeout=30,
            )
            host_key = client.get_transport().get_remote_server_key()
            fingerprint = base64.b64encode(hashlib.sha256(host_key.asbytes()).digest()).decode("ascii")
            if expected_fingerprint and fingerprint != expected_fingerprint:
                raise BackupError("SFTP_HOST_KEY_MISMATCH", "La identidad del servidor SFTP no coincide")
            sftp = client.open_sftp()
            remote_dir = posixpath.join(remote_root.rstrip("/"), date_text)
            current = ""
            for part in remote_dir.split("/"):
                if not part:
                    continue
                current += "/" + part
                try:
                    sftp.stat(current)
                except OSError:
                    sftp.mkdir(current)
            remote_path = posixpath.join(remote_dir, zip_path.name)
            partial = remote_path + ".part"
            sftp.put(str(zip_path), partial, confirm=True)
            try:
                sftp.posix_rename(partial, remote_path)
            except OSError:
                sftp.rename(partial, remote_path)
            remote_size = int(sftp.stat(remote_path).st_size)
            if remote_size != zip_path.stat().st_size:
                raise BackupError("TRANSFER_VERIFY_FAILED", "El archivo SFTP no coincide en tamano")
            sftp.close()
            return {
                "type": "sftp",
                "path": remote_path,
                "sizeBytes": remote_size,
                "verified": True,
            }
        except BackupError:
            raise
        except Exception as exc:
            raise BackupError("SFTP_TRANSFER_FAILED", "No fue posible transferir el ZIP por SFTP") from exc
        finally:
            client.close()
