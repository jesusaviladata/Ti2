"""
SQL Server backup operations via pyodbc.
All blocking calls run in a thread-pool executor to avoid blocking the event loop.
"""

import asyncio
import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pyodbc
from fastapi import HTTPException, status

from app.core.config import settings

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sqlsrv")


def safe_error(exc: Exception) -> str:
    """Redacta credenciales (PWD/UID) de los mensajes de error antes de exponerlos."""
    return re.sub(r"(PWD|UID|PASSWORD|USER)=[^;]*", r"\1=***",
                  str(exc), flags=re.IGNORECASE)[:512]


def _conn() -> pyodbc.Connection:
    """Create a synchronous SQL Server connection."""
    cs = (
        f"DRIVER={{{settings.SQLSERVER_DRIVER}}};"
        f"SERVER={settings.SQLSERVER_SERVER},{settings.SQLSERVER_PORT};"
        f"DATABASE=master;"
        f"UID={settings.SQLSERVER_USER};"
        f"PWD={settings.SQLSERVER_PASSWORD};"
        "TrustServerCertificate=yes;"
    )
    try:
        return pyodbc.connect(cs, timeout=10)
    except pyodbc.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo conectar a SQL Server: {safe_error(exc)}",
        )


async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, fn, *args)


# ── Public async API ──────────────────────────────────────────────────────────

async def list_databases() -> list[str]:
    """Return user databases (excludes system DBs)."""
    return await _run(_sync_list_databases)


async def execute_backup(
    db_name: str,
    backup_type: str,       # "full" | "differential" | "log"
    destination_path: str,  # full local path on the SQL Server host
    compress: bool = True,
) -> dict:
    """
    Execute BACKUP DATABASE or BACKUP LOG.
    Returns dict with file_path, file_size_bytes, sha256_hash.
    """
    _validate_db_name(db_name)
    Path(destination_path).parent.mkdir(parents=True, exist_ok=True)
    return await _run(_sync_execute_backup, db_name, backup_type, destination_path, compress)


async def verify_backup(file_path: str) -> dict:
    """RESTORE VERIFYONLY and compute SHA-256 of the backup file."""
    return await _run(_sync_verify_backup, file_path)


async def test_connection() -> bool:
    return await _run(_sync_test_connection)


# ── Sync implementations ──────────────────────────────────────────────────────

def _sync_list_databases() -> list[str]:
    with _conn() as cn:
        cur = cn.execute(
            "SELECT name FROM sys.databases "
            "WHERE database_id > 4 AND state_desc = 'ONLINE' "
            "ORDER BY name"
        )
        return [row[0] for row in cur.fetchall()]


def _stripe_paths(base: str) -> list[str]:
    """Divide el destino en N archivos paralelos (striping) si el tuning lo pide."""
    n = settings.SQLSERVER_BACKUP_STRIPES
    if n <= 1:
        return [base]
    p = Path(base)
    return [str(p.with_name(f"{p.stem}_part{i + 1}of{n}{p.suffix}")) for i in range(n)]


def _sync_execute_backup(db_name: str, backup_type: str, destination_path: str, compress: bool) -> dict:
    if backup_type not in ("full", "differential", "log"):
        raise ValueError(f"Unknown backup_type: {backup_type}")

    # CHECKSUM (integridad) + BUFFERCOUNT/MAXTRANSFERSIZE (throughput de I/O)
    base_opts = (f"FORMAT, INIT, CHECKSUM, STATS = 10, "
                 f"BUFFERCOUNT = {settings.SQLSERVER_BACKUP_BUFFERCOUNT}, "
                 f"MAXTRANSFERSIZE = 4194304")
    verb  = "BACKUP LOG" if backup_type == "log" else "BACKUP DATABASE"
    diff  = "DIFFERENTIAL, " if backup_type == "differential" else ""
    paths = _stripe_paths(destination_path)
    disk_clause = ", ".join(["DISK = ?"] * len(paths))

    def _sql(compression: bool) -> str:
        comp = "COMPRESSION, " if compression else ""
        return f"{verb} [{db_name}] TO {disk_clause} WITH {comp}{diff}{base_opts}"

    with _conn() as cn:
        # Intentar con compresión; si la edición no la soporta, reintentar sin ella.
        try:
            cn.execute(_sql(compress), *paths)
        except pyodbc.Error as exc:
            if compress and "compress" in str(exc).lower():
                cn.execute(_sql(False), *paths)
            else:
                raise
        cn.commit()

    file_size = sum(os.path.getsize(p) for p in paths if os.path.exists(p))
    sha256 = _hash_files(paths)
    return {
        "file_path": ";".join(paths) if len(paths) > 1 else paths[0],
        "file_size_bytes": file_size,
        "sha256_hash": sha256,
    }


def _sync_verify_backup(file_path: str) -> dict:
    paths = file_path.split(";")
    disk_clause = ", ".join(["DISK = ?"] * len(paths))
    with _conn() as cn:
        cn.execute(f"RESTORE VERIFYONLY FROM {disk_clause} WITH CHECKSUM", *paths)
    return {"valid": True, "sha256_hash": _hash_files(paths)}


def _sync_test_connection() -> bool:
    try:
        with _conn() as cn:
            cn.execute("SELECT 1")
        return True
    except Exception:
        return False


def _hash_file(path: str) -> str:
    return _hash_files([path])


def _hash_files(paths: list[str]) -> str:
    """SHA-256 combinado sobre uno o varios archivos (stripes), en orden."""
    h = hashlib.sha256()
    try:
        for path in paths:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _validate_db_name(name: str) -> None:
    """Prevent SQL injection in database names used in dynamic SQL."""
    if not re.match(r"^[A-Za-z0-9_\-\.]{1,128}$", name):
        raise HTTPException(status_code=400, detail="Nombre de base de datos inválido")


def build_backup_path(db_name: str, backup_type: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ext = ".bak" if backup_type != "log" else ".trn"
    filename = f"{db_name}_{backup_type.upper()}_{ts}{ext}"
    return str(Path(settings.SQLSERVER_BACKUP_PATH) / filename)
