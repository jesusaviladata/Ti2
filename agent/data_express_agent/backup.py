from __future__ import annotations

import base64
import hashlib
import json
import os
import posixpath
import re
import shutil
import threading
import time
import zipfile
import io
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any


ProgressCallback = Callable[[dict[str, Any]], None]
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_CLEANUP_MARKER = ".dataexpress-cleanup-ready.json"
_BACKUP_TYPE_FOLDERS = {
    "full": "FULL",
    "differential": "DIFERENCIAL",
    "log": "LOG",
}


class BackupError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _diagnostic_error_message(exc: Exception) -> str:
    """Expose a bounded, credential-free database error to the operator."""
    detail = " ".join(str(exc).replace("\r", " ").replace("\n", " ").split())
    detail = re.sub(r"(?i)(password|pwd)\s*=\s*[^;\s]+", r"\1=***", detail)
    return detail[:700]


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


def backup_member_name(database: str, date_text: str, backup_type: str) -> str:
    safe_database = _safe_database_name(database)
    if backup_type == "full":
        suffix, extension = "", ".bak"
    elif backup_type == "differential":
        suffix, extension = "_DIF", ".bak"
    elif backup_type == "log":
        suffix, extension = "_LOG", ".trn"
    else:
        raise BackupError("BACKUP_TYPE_INVALID", "El tipo de backup no es valido")
    return f"{safe_database}_{date_text}{suffix}{extension}"


def daily_archive_path(root: Path, date_text: str, backup_type: str) -> Path:
    try:
        folder = _BACKUP_TYPE_FOLDERS[backup_type]
    except KeyError as exc:
        raise BackupError("BACKUP_TYPE_INVALID", "El tipo de backup no es valido") from exc
    dated_root = root / date_text
    if backup_type == "full":
        return dated_root / f"Backup_{date_text}.zip"
    return dated_root / folder / f"Backup_{date_text}.zip"


def _transfer_type_folder(backup_type: str) -> str | None:
    if backup_type == "full":
        return None
    try:
        return _BACKUP_TYPE_FOLDERS[backup_type]
    except KeyError as exc:
        raise BackupError("BACKUP_TYPE_INVALID", "El tipo de backup no es valido") from exc


def _delivery_location(zip_path: Path) -> tuple[str, str | None]:
    """Return the dated destination and optional type folder.

    Legacy 0.4.1 Full archives under Fecha/FULL remain deliverable. New Full
    archives live directly under Fecha while other types retain their folder.
    """
    parent_name = zip_path.parent.name
    if parent_name in set(_BACKUP_TYPE_FOLDERS.values()):
        date_text = zip_path.parent.parent.name
        type_folder: str | None = parent_name
    else:
        date_text = parent_name
        type_folder = None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
        raise BackupError("DELIVERY_SOURCE_INVALID", "La ruta diaria del ZIP no es valida")
    return date_text, type_folder


def _sql_unicode_literal(value: str) -> str:
    """Return a safely escaped SQL Server Unicode string literal.

    BACKUP/RESTORE statements on SQL Server Express do not reliably accept ODBC
    parameter markers for their DISK path.  Paths here are agent-generated from
    a validated root and database names are separately allow-listed.
    """
    return "N'" + value.replace("'", "''") + "'"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_host_key_sha256(value: str) -> str:
    """Accept both OpenSSH's display form and padded Base64 configuration."""
    fingerprint = value.strip()
    if fingerprint.lower().startswith("sha256:"):
        fingerprint = fingerprint[7:]
    return fingerprint.rstrip("=")


def _remove_work_files(files: list[Path], work_dir: Path) -> dict[str, Any]:
    """Remove batch source files without turning a valid backup into a failure.

    Compression and an optional remote transfer have already succeeded when this
    helper runs.  A locked file is retained and reported so a duplicated remote
    backup is not created merely because local housekeeping could not finish.
    """
    deleted: list[str] = []
    retained: list[str] = []
    for path in files:
        try:
            path.unlink()
            deleted.append(path.name)
        except FileNotFoundError:
            deleted.append(path.name)
        except OSError:
            retained.append(str(path))

    if not retained:
        try:
            work_dir.rmdir()
            work_dir.parent.rmdir()
        except OSError:
            # Another retained/recovery batch may still exist below .work.
            pass
    return {
        "attemptedFiles": len(files),
        "deletedFiles": deleted,
        "retainedFiles": retained,
        "complete": not retained,
    }


def _wait_for_backup_file(
    path: Path, *, timeout_seconds: float = 90, sleep: Callable[[float], None] = time.sleep
) -> bool:
    """Wait for SQL Server to finish materializing a backup file on disk."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            if path.is_file() and path.stat().st_size > 0:
                return True
        except OSError:
            pass
        if time.monotonic() >= deadline:
            return False
        sleep(0.5)


def _consume_sql_results(cursor: Any) -> None:
    """Drain informational result sets so SQL Server has completed BACKUP."""
    nextset = getattr(cursor, "nextset", None)
    if nextset is None:
        return
    while nextset():
        pass


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
        cleanup_submit: Callable[[list[Path], Path], dict[str, Any]] | None = None,
        disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
        size_history: dict[str, int] | None = None,
    ):
        self.sql_profiles = sql_profiles
        self.destination_profiles = destination_profiles
        self._connect_override = connect
        self.now = now or datetime.now
        self._cleanup_submit = cleanup_submit
        self.disk_usage = disk_usage
        self.size_history = size_history or {}

    def _allocated_database_bytes(
        self, connection: Any, databases: list[str]
    ) -> dict[str, int]:
        literals = ",".join(_sql_unicode_literal(name) for name in databases)
        rows = connection.execute(
            "SELECT DB_NAME(database_id), SUM(CAST(size AS bigint)) * 8192 "
            "FROM sys.master_files "
            f"WHERE DB_NAME(database_id) IN ({literals}) GROUP BY database_id"
        ).fetchall()
        return {str(row[0]): max(0, int(row[1] or 0)) for row in rows}

    def _preflight_space(
        self,
        connection: Any,
        databases: list[str],
        configured_root: Path,
        payload: dict[str, Any],
    ) -> dict[str, int]:
        allocated = self._allocated_database_bytes(connection, databases)
        missing_estimates = [
            name
            for name in databases
            if max(int(self.size_history.get(name, 0)), int(allocated.get(name, 0))) <= 0
        ]
        if missing_estimates:
            raise BackupError(
                "BACKUP_SPACE_ESTIMATE_FAILED",
                "No fue posible calcular de forma segura el espacio requerido para: "
                + ", ".join(missing_estimates),
            )
        estimates = [
            max(int(self.size_history.get(name, 0)), int(allocated.get(name, 0)))
            for name in databases
        ]
        estimated_backup_bytes = sum(estimates)
        # The .bak files and the temporary ZIP coexist until integrity checks pass.
        estimated_work_bytes = estimated_backup_bytes * 2
        thresholds = payload.get("storageThresholds") or {}
        critical_reserve = int(
            thresholds.get("criticalFreeBytes") or 10 * 1024**3
        )
        usage = self.disk_usage(configured_root)
        free_bytes = int(usage.free)
        if free_bytes - estimated_work_bytes < critical_reserve:
            raise BackupError(
                "BACKUP_SPACE_INSUFFICIENT",
                "Espacio insuficiente antes de iniciar SQL Server "
                f"(libre={free_bytes}, estimado={estimated_work_bytes}, "
                f"reserva={critical_reserve}, volumen={configured_root.anchor or configured_root})",
            )
        return {
            "freeBytes": free_bytes,
            "estimatedBackupBytes": estimated_backup_bytes,
            "estimatedWorkBytes": estimated_work_bytes,
            "criticalReserveBytes": critical_reserve,
        }

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

    @staticmethod
    def _build_archive_atomically(
        files: list[Path],
        final_path: Path,
        manifest: dict[str, Any],
        run_id: str,
    ) -> None:
        temporary = final_path.with_name(f".{final_path.name}.{run_id}.tmp")
        try:
            with zipfile.ZipFile(
                temporary,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=1,
                allowZip64=True,
            ) as archive:
                for file_path in files:
                    archive.write(file_path, arcname=file_path.name)
                archive.writestr(
                    "manifest.json",
                    json.dumps(
                        manifest,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            with zipfile.ZipFile(temporary, "r") as archive:
                if archive.testzip() is not None:
                    raise BackupError(
                        "ZIP_INTEGRITY_FAILED",
                        "El ZIP generado no supero la validacion",
                    )
                if "manifest.json" not in archive.namelist():
                    raise BackupError(
                        "ZIP_MANIFEST_MISSING", "El ZIP no contiene su manifiesto"
                    )
            os.replace(temporary, final_path)
        finally:
            temporary.unlink(missing_ok=True)

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
        try:
            with self._connect(profile) as connection:
                preflight = self._preflight_space(
                    connection, databases, configured_root, payload
                )
        except BackupError:
            raise
        except Exception as exc:
            raise BackupError(
                "BACKUP_SPACE_CHECK_FAILED",
                "No fue posible estimar el espacio requerido para el backup",
            ) from exc
        self._resume_pending_cleanups(configured_root)
        date_text = self.now().strftime("%Y-%m-%d")
        dated_dir = configured_root / date_text
        zip_path = daily_archive_path(configured_root, date_text, backup_type)
        try:
            zip_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise BackupError("BACKUP_DIRECTORY_FAILED", "No fue posible crear la carpeta diaria") from exc

        run_id = str(payload.get("runId") or self.now().strftime("%Y%m%d%H%M%S"))
        if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", run_id):
            raise BackupError("RUN_ID_INVALID", "El identificador de ejecucion no es valido")
        work_dir = dated_dir / ".work" / run_id
        try:
            work_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise BackupError(
                "BACKUP_WORK_DIRECTORY_FAILED",
                "No fue posible crear el espacio temporal del backup",
            ) from exc
        files: list[Path] = []
        database_results: list[dict[str, Any]] = []
        try:
            with self._connect(profile) as connection:
                for index, database in enumerate(databases, start=1):
                    if progress:
                        progress(
                            {
                                "phase": "creating_bak",
                                "processedUnits": index - 1,
                                "totalUnits": len(databases),
                                "foundCount": len(files),
                                "database": database,
                            }
                        )
                    file_path = work_dir / backup_member_name(
                        database, date_text, backup_type
                    )
                    verification_method = self._backup_database(
                        connection,
                        database,
                        backup_type,
                        file_path,
                        phase=(
                            lambda current_phase, database=database, index=index: progress(
                                {
                                    "phase": current_phase,
                                    "processedUnits": index - 1,
                                    "totalUnits": len(databases),
                                    "foundCount": len(files),
                                    "database": database,
                                }
                            )
                            if progress
                            else None
                        ),
                    )
                    if not _wait_for_backup_file(file_path):
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
                    if progress:
                        progress(
                            {
                                "phase": "backup_ready",
                                "processedUnits": index,
                                "totalUnits": len(databases),
                                "foundCount": len(files),
                                "database": database,
                                "details": database_results[-1],
                            }
                        )
        except BackupError:
            raise
        except Exception as exc:
            detail = _diagnostic_error_message(exc)
            message = "SQL Server no pudo completar el backup"
            if detail:
                message = f"{message}: {detail}"
            raise BackupError("BACKUP_DATABASE_FAILED", message) from exc

        if progress:
            progress(
                {
                    "phase": "compressing",
                    "processedUnits": len(databases),
                    "totalUnits": len(databases),
                    "foundCount": len(files),
                }
            )
        manifest = {
            "version": 1,
            "runId": run_id,
            "createdAt": self.now().isoformat(),
            "backupType": backup_type,
            "origin": dict(payload.get("origin") or {}),
            "databases": database_results,
        }
        try:
            self._build_archive_atomically(files, zip_path, manifest, run_id)
        except BackupError:
            raise
        except (OSError, zipfile.BadZipFile) as exc:
            raise BackupError("ZIP_CREATION_FAILED", "No fue posible crear el ZIP diario") from exc

        zip_size = zip_path.stat().st_size
        zip_sha256 = _sha256(zip_path)
        if progress:
            progress(
                {
                    "phase": "archive_ready",
                    "processedUnits": len(databases),
                    "totalUnits": len(databases),
                    "foundCount": len(files),
                    "details": {
                        "zipPath": str(zip_path),
                        "zipSizeBytes": zip_size,
                        "zipSha256": zip_sha256,
                    },
                }
            )

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
            transfer_result = self._transfer(
                zip_path,
                destination,
                date_text,
                _transfer_type_folder(backup_type),
            )

        cleanup_result = self._schedule_cleanup(files, work_dir)

        result = {
            "runId": run_id,
            "sqlProfileId": sql_profile_id,
            "backupType": backup_type,
            "folder": str(zip_path.parent),
            "zipPath": str(zip_path),
            "zipFileName": zip_path.name,
            "zipSizeBytes": zip_size,
            "zipSha256": zip_sha256,
            "databases": database_results,
            "transfer": transfer_result,
            "localSourceCleanup": cleanup_result,
            "storagePreflight": preflight,
            "origin": manifest["origin"],
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

    def retry_delivery(
        self,
        payload: dict[str, Any],
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        run_id = str(payload.get("runId") or "")
        if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", run_id):
            raise BackupError("RUN_ID_INVALID", "El identificador de ejecución no es válido")
        destination_profile_id = str(payload.get("destinationProfileId") or "")
        destination = _profile(self.destination_profiles, destination_profile_id, "destination")
        zip_path = Path(str(payload.get("zipPath") or ""))
        expected_sha256 = str(payload.get("zipSha256") or "")
        sql_profile = _profile(self.sql_profiles, str(payload.get("sqlProfileId") or ""), "sql")
        configured_root = Path(str(sql_profile.get("backupRoot") or "D:\\"))
        try:
            zip_path.resolve(strict=True).relative_to(configured_root.resolve(strict=True))
        except (OSError, ValueError, RuntimeError) as exc:
            raise BackupError("DELIVERY_SOURCE_INVALID", "El ZIP no pertenece a la raíz de backup") from exc
        if not zip_path.is_file() or not expected_sha256 or _sha256(zip_path) != expected_sha256:
            raise BackupError("DELIVERY_SOURCE_CHANGED", "El ZIP local cambió o ya no está disponible")
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                if archive.testzip() is not None:
                    raise BackupError("ZIP_INTEGRITY_FAILED", "El ZIP no superó la validación")
                member_names = [Path(item.filename).name for item in archive.infolist() if not item.is_dir()]
        except zipfile.BadZipFile as exc:
            raise BackupError("ZIP_INTEGRITY_FAILED", "El ZIP no superó la validación") from exc
        if progress:
            progress({"phase": "transferring", "processedUnits": 0, "totalUnits": 1, "foundCount": 0})
        date_text, type_folder = _delivery_location(zip_path)
        transfer = self._transfer(zip_path, destination, date_text, type_folder)
        dated_dir = zip_path.parent.parent if type_folder else zip_path.parent
        work_dir = dated_dir / ".work" / run_id
        files = [work_dir / name for name in member_names if Path(name).name == name]
        cleanup = self._schedule_cleanup(files, work_dir) if files else {"scheduled": False, "status": "no_sources"}
        return {
            "runId": run_id,
            "zipPath": str(zip_path),
            "zipSizeBytes": zip_path.stat().st_size,
            "zipSha256": expected_sha256,
            "transfer": transfer,
            "localSourceCleanup": cleanup,
        }

    def _schedule_cleanup(self, files: list[Path], work_dir: Path) -> dict[str, Any]:
        if self._cleanup_submit is not None:
            return self._cleanup_submit(files, work_dir)
        marker = work_dir / _CLEANUP_MARKER
        try:
            temporary = marker.with_suffix(marker.suffix + ".tmp")
            temporary.write_text(
                json.dumps({"files": [path.name for path in files]}, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temporary, marker)
            self._start_cleanup_thread(marker, files, work_dir)
            return {
                "scheduled": True,
                "status": "background",
                "attemptedFiles": len(files),
            }
        except OSError:
            return {
                "scheduled": False,
                "status": "retained",
                "attemptedFiles": len(files),
                "retainedFiles": [str(path) for path in files],
            }

    @staticmethod
    def _start_cleanup_thread(marker: Path, files: list[Path], work_dir: Path) -> None:
        def cleanup() -> None:
            result = _remove_work_files(files, work_dir)
            if not result["complete"]:
                return
            try:
                marker.unlink(missing_ok=True)
                work_dir.rmdir()
                work_dir.parent.rmdir()
            except OSError:
                pass

        threading.Thread(
            target=cleanup,
            name=f"dataexpress-cleanup-{work_dir.name}",
            daemon=True,
        ).start()

    def _resume_pending_cleanups(self, configured_root: Path) -> None:
        """Retry only work directories explicitly marked after a successful ZIP/transfer."""
        try:
            markers = list(configured_root.glob(f"*/.work/*/{_CLEANUP_MARKER}"))[:100]
        except OSError:
            return
        for marker in markers:
            try:
                document = json.loads(marker.read_text(encoding="utf-8"))
                names = [str(item) for item in document.get("files", [])]
                if not names or any(Path(name).name != name for name in names):
                    continue
                work_dir = marker.parent
                files = [work_dir / name for name in names]
                self._start_cleanup_thread(marker, files, work_dir)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue

    def _backup_database(
        self,
        connection: Any,
        database: str,
        backup_type: str,
        file_path: Path,
        *,
        phase: Callable[[str], None] | None = None,
    ) -> str:
        verb = "BACKUP LOG" if backup_type == "log" else "BACKUP DATABASE"
        differential = "DIFFERENTIAL, " if backup_type == "differential" else ""
        quoted_database = database.replace("]", "]]" )
        disk_path = _sql_unicode_literal(str(file_path))
        sql = (
            f"{verb} [{quoted_database}] TO DISK = {disk_path} WITH "
            f"{differential}FORMAT, INIT, CHECKSUM, STATS = 10"
        )
        # SQL Server Express does not support backup compression.  Using the
        # portable statement directly also avoids a failed first attempt on
        # editions where compression is disabled by policy.
        cursor = connection.execute(sql)
        _consume_sql_results(cursor)
        if phase:
            phase("validating_bak")
        try:
            cursor = connection.execute(f"RESTORE VERIFYONLY FROM DISK = {disk_path} WITH CHECKSUM")
            _consume_sql_results(cursor)
        except Exception as exc:
            detail = _diagnostic_error_message(exc)
            message = "SQL Server no pudo validar el archivo .bak"
            if detail:
                message = f"{message}: {detail}"
            raise BackupError("BACKUP_VALIDATION_FAILED", message) from exc
        return "restore_verifyonly"

    def _transfer(
        self,
        zip_path: Path,
        destination: dict[str, Any],
        date_text: str,
        type_folder: str | None,
    ) -> dict[str, Any]:
        destination_type = str(destination.get("type") or "").lower()
        if destination_type == "smb":
            return self._transfer_smb(zip_path, destination, date_text, type_folder)
        if destination_type == "sftp":
            return self._transfer_sftp(zip_path, destination, date_text, type_folder)
        raise BackupError("DESTINATION_TYPE_INVALID", "El tipo de destino no esta soportado")

    @staticmethod
    def _transfer_smb(
        zip_path: Path,
        destination: dict[str, Any],
        date_text: str,
        type_folder: str | None,
    ) -> dict[str, Any]:
        root = Path(str(destination.get("path") or ""))
        if not str(root).startswith(("\\\\", "//")):
            raise BackupError("SMB_PATH_INVALID", "El destino SMB debe ser una ruta UNC")
        target_dir = root / date_text
        if type_folder:
            target_dir /= type_folder
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / zip_path.name
        partial = target.with_suffix(target.suffix + ".part")
        shutil.copy2(zip_path, partial)
        os.replace(partial, target)
        if target.stat().st_size != zip_path.stat().st_size:
            raise BackupError("TRANSFER_VERIFY_FAILED", "El archivo SMB no coincide en tamano")
        if _sha256(target) != _sha256(zip_path):
            raise BackupError("TRANSFER_VERIFY_FAILED", "El archivo SMB no coincide en contenido")
        return {
            "type": "smb",
            "path": str(target),
            "sizeBytes": target.stat().st_size,
            "sha256": _sha256(target),
            "verified": True,
        }

    @staticmethod
    def _transfer_sftp(
        zip_path: Path,
        destination: dict[str, Any],
        date_text: str,
        type_folder: str | None,
    ) -> dict[str, Any]:
        try:
            import paramiko
        except ImportError as exc:
            raise BackupError("PARAMIKO_UNAVAILABLE", "El soporte SFTP no esta disponible") from exc
        host = str(destination.get("host") or "").strip()
        username = str(destination.get("username") or "").strip()
        key_path = str(destination.get("privateKeyPath") or "").strip()
        key_data = str(destination.get("privateKey") or "").strip()
        remote_root = str(destination.get("path") or "").strip()
        expected_fingerprint = _normalize_host_key_sha256(
            str(destination.get("hostKeySha256") or "")
        )
        if not host or not username or (not key_path and not key_data) or not remote_root.startswith("/"):
            raise BackupError("SFTP_PROFILE_INVALID", "El perfil SFTP esta incompleto")
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        if expected_fingerprint:
            class PinnedHostKeyPolicy(paramiko.MissingHostKeyPolicy):
                def missing_host_key(self, _client, _hostname, key):
                    actual = base64.b64encode(
                        hashlib.sha256(key.asbytes()).digest()
                    ).decode("ascii").rstrip("=")
                    if actual != expected_fingerprint:
                        raise BackupError(
                            "SFTP_HOST_KEY_MISMATCH",
                            "La identidad del servidor SFTP no coincide",
                        )

            client.set_missing_host_key_policy(PinnedHostKeyPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            connect_options = {
                "hostname": host,
                "port": int(destination.get("port") or 22),
                "username": username,
                "look_for_keys": False,
                "allow_agent": False,
                "timeout": 30,
            }
            if key_data:
                password = str(destination.get("privateKeyPassphrase") or "") or None
                parsed_key = None
                for key_type in (
                    paramiko.Ed25519Key,
                    paramiko.RSAKey,
                    paramiko.ECDSAKey,
                ):
                    try:
                        parsed_key = key_type.from_private_key(
                            io.StringIO(key_data), password=password
                        )
                        break
                    except (paramiko.SSHException, ValueError):
                        continue
                if parsed_key is None:
                    raise BackupError("SFTP_PRIVATE_KEY_INVALID", "La llave privada SFTP no es válida")
                connect_options["pkey"] = parsed_key
            else:
                connect_options["key_filename"] = key_path
            client.connect(
                **connect_options,
            )
            host_key = client.get_transport().get_remote_server_key()
            fingerprint = base64.b64encode(
                hashlib.sha256(host_key.asbytes()).digest()
            ).decode("ascii").rstrip("=")
            if expected_fingerprint and fingerprint != expected_fingerprint:
                raise BackupError("SFTP_HOST_KEY_MISMATCH", "La identidad del servidor SFTP no coincide")
            sftp = client.open_sftp()
            remote_dir = posixpath.join(remote_root.rstrip("/"), date_text)
            if type_folder:
                remote_dir = posixpath.join(remote_dir, type_folder)
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
            remote_digest = hashlib.sha256()
            with sftp.open(remote_path, "rb") as remote_stream:
                for chunk in iter(lambda: remote_stream.read(1024 * 1024), b""):
                    remote_digest.update(chunk)
            remote_sha256 = remote_digest.hexdigest()
            if remote_sha256 != _sha256(zip_path):
                raise BackupError("TRANSFER_VERIFY_FAILED", "El archivo SFTP no coincide en contenido")
            sftp.close()
            return {
                "type": "sftp",
                "path": remote_path,
                "sizeBytes": remote_size,
                "sha256": remote_sha256,
                "verified": True,
            }
        except BackupError:
            raise
        except Exception as exc:
            raise BackupError("SFTP_TRANSFER_FAILED", "No fue posible transferir el ZIP por SFTP") from exc
        finally:
            client.close()
