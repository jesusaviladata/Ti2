from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable


ProgressCallback = Callable[[dict[str, Any]], None]
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_SCHEMA_VERSION = 1


class FileBackupError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ScannedFile:
    source_index: int
    source_path: Path
    relative_path: str
    path: Path
    size: int
    mtime_ns: int

    @property
    def key(self) -> str:
        return f"{self.source_index}:{self.relative_path.casefold()}"

    @property
    def archive_path(self) -> Path:
        return Path(f"Fuente-{self.source_index}") / Path(self.relative_path)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_label(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or "Respaldo")[:100]


def _is_root(path: Path) -> bool:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        resolved = path.absolute()
    return resolved.parent == resolved


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    attributes = int(getattr(info, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return path.is_symlink() or bool(attributes & reparse_flag)


class FileBackupCatalog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_state (
                    task_id TEXT PRIMARY KEY,
                    last_run_id TEXT,
                    last_full_run_id TEXT,
                    last_chain_id TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS catalog_entries (
                    task_id TEXT NOT NULL,
                    file_key TEXT NOT NULL,
                    source_index INTEGER NOT NULL,
                    relative_path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    full_size INTEGER,
                    full_mtime_ns INTEGER,
                    full_sha256 TEXT,
                    last_run_id TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (task_id, file_key)
                );
                CREATE TABLE IF NOT EXISTS local_runs (
                    run_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    chain_id TEXT NOT NULL,
                    artifact_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    manifest_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checkpoints (
                    run_id TEXT NOT NULL,
                    file_key TEXT NOT NULL,
                    destination_path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    PRIMARY KEY (run_id, file_key)
                );
                """
            )
            current = db.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
            if current is None:
                db.execute(
                    "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
                    (str(_SCHEMA_VERSION),),
                )
                db.execute(
                    "INSERT INTO metadata(key, value) VALUES('catalog_revision', '0')"
                )
            elif int(current["value"]) != _SCHEMA_VERSION:
                raise FileBackupError(
                    "FILE_CATALOG_VERSION_UNSUPPORTED",
                    "El catálogo local requiere una migración compatible",
                )

    @property
    def revision(self) -> int:
        with self.connect() as db:
            row = db.execute(
                "SELECT value FROM metadata WHERE key = 'catalog_revision'"
            ).fetchone()
            return int(row["value"] if row else 0)


class FileBackupExecutor:
    def __init__(
        self,
        data_dir: Path,
        *,
        destination_profiles: tuple[dict[str, Any], ...] = (),
        now: Callable[[], datetime] | None = None,
        disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
        allow_test_paths: bool = False,
    ):
        self.data_dir = Path(data_dir)
        self.catalog = FileBackupCatalog(self.data_dir / "file-backup.db")
        self.destination_profiles = destination_profiles
        self.now = now or datetime.now
        self.disk_usage = disk_usage
        self.allow_test_paths = allow_test_paths

    @property
    def catalog_revision(self) -> int:
        return self.catalog.revision

    def execute(
        self,
        command_type: str,
        payload: dict[str, Any],
        progress: ProgressCallback,
    ) -> dict[str, Any]:
        handlers = {
            "simulate_file_backup": self.simulate,
            "run_file_backup": self.run,
            "resume_file_backup": self.run,
            "test_file_destination": self.test_destination,
        }
        handler = handlers.get(command_type)
        if handler is None:
            raise FileBackupError(
                "FILE_BACKUP_COMMAND_UNAVAILABLE",
                "La operación de respaldo de archivos aún no está disponible",
            )
        return handler(payload, progress=progress)

    def _destination(self, profile_id: str) -> dict[str, Any]:
        for profile in self.destination_profiles:
            if str(profile.get("id") or "") == profile_id:
                return profile
        raise FileBackupError(
            "FILE_BACKUP_DESTINATION_NOT_FOUND",
            "El destino no está aplicado en este agente",
        )

    def _destination_root(self, payload: dict[str, Any]) -> Path:
        profile = self._destination(str(payload.get("destinationProfileId") or ""))
        destination_type = str(profile.get("type") or "").lower()
        if destination_type not in {"local", "smb", "smb_direct"}:
            raise FileBackupError(
                "FILE_BACKUP_DESTINATION_UNSUPPORTED",
                "Esta fase admite destinos locales o SMB",
            )
        root_text = str(profile.get("path") or "").strip()
        if not root_text:
            raise FileBackupError(
                "FILE_BACKUP_DESTINATION_INVALID", "El destino no tiene una ruta"
            )
        if destination_type in {"smb", "smb_direct"} and not (
            root_text.startswith(("\\\\", "//")) or self.allow_test_paths
        ):
            raise FileBackupError(
                "FILE_BACKUP_DESTINATION_INVALID", "El destino SMB debe ser UNC"
            )
        return Path(root_text)

    @staticmethod
    def _validate_payload(payload: dict[str, Any]) -> tuple[str, str, str]:
        task_id = str(payload.get("taskId") or "").strip()
        run_id = str(payload.get("fileRunId") or "").strip()
        strategy = str(payload.get("strategy") or "full").lower()
        if not task_id or len(task_id) > 128:
            raise FileBackupError("FILE_BACKUP_TASK_INVALID", "La tarea no es válida")
        if not _SAFE_RUN_ID.fullmatch(run_id):
            raise FileBackupError(
                "FILE_BACKUP_RUN_INVALID", "La ejecución no es válida"
            )
        if strategy not in {"full", "incremental", "differential"}:
            raise FileBackupError(
                "FILE_BACKUP_STRATEGY_INVALID", "La estrategia no es válida"
            )
        if str(payload.get("format") or "direct").lower() != "direct":
            raise FileBackupError(
                "FILE_BACKUP_FORMAT_UNSUPPORTED",
                "ZIP64 se habilitará después de validar el formato directo",
            )
        return task_id, run_id, strategy

    def _sources(self, payload: dict[str, Any]) -> list[tuple[Path, bool]]:
        values = payload.get("sources") or []
        if not isinstance(values, list) or not 1 <= len(values) <= 64:
            raise FileBackupError(
                "FILE_BACKUP_SOURCE_REQUIRED", "Seleccione al menos una fuente"
            )
        result: list[tuple[Path, bool]] = []
        seen: set[str] = set()
        for raw in values:
            path = Path(str(raw.get("path") or ""))
            try:
                resolved = path.resolve(strict=True)
            except OSError as exc:
                raise FileBackupError(
                    "FILE_BACKUP_SOURCE_UNAVAILABLE",
                    f"No fue posible abrir la fuente {path}",
                ) from exc
            if not resolved.is_dir():
                raise FileBackupError(
                    "FILE_BACKUP_SOURCE_INVALID", "La fuente debe ser una carpeta"
                )
            if _is_root(resolved):
                raise FileBackupError(
                    "FILE_BACKUP_SOURCE_ROOT_FORBIDDEN",
                    "No se permite respaldar una raíz completa",
                )
            key = os.path.normcase(str(resolved))
            if key in seen:
                continue
            seen.add(key)
            result.append((resolved, bool(raw.get("includeSubfolders", True))))
        return result

    @staticmethod
    def _matches_filter(relative: str, path: Path, rule: dict[str, Any]) -> bool:
        operator = str(rule.get("operator") or "").lower()
        pattern = str(rule.get("pattern") or "")
        normalized = relative.replace("\\", "/")
        if operator == "extension":
            expected = pattern.lower()
            if expected and not expected.startswith("."):
                expected = "." + expected
            return path.suffix.lower() == expected
        if operator == "relative_path":
            return fnmatch.fnmatch(normalized.casefold(), pattern.replace("\\", "/").casefold())
        if operator == "glob":
            return fnmatch.fnmatch(path.name.casefold(), pattern.casefold()) or fnmatch.fnmatch(
                normalized.casefold(), pattern.replace("\\", "/").casefold()
            )
        return False

    def _included(self, relative: str, path: Path, filters: list[dict[str, Any]]) -> bool:
        enabled = [item for item in filters if item.get("isEnabled", True)]
        includes = [item for item in enabled if str(item.get("kind")) == "include"]
        excludes = [item for item in enabled if str(item.get("kind")) == "exclude"]
        if includes and not any(self._matches_filter(relative, path, item) for item in includes):
            return False
        return not any(self._matches_filter(relative, path, item) for item in excludes)

    def _scan(
        self,
        payload: dict[str, Any],
        progress: ProgressCallback,
    ) -> tuple[list[ScannedFile], int]:
        filters = list(payload.get("filters") or [])
        files: list[ScannedFile] = []
        excluded = 0
        for source_index, (source, recursive) in enumerate(self._sources(payload), start=1):
            iterator: Iterable[Path] = source.rglob("*") if recursive else source.glob("*")
            for path in iterator:
                if _is_reparse(path):
                    continue
                try:
                    if not path.is_file():
                        continue
                    relative = str(path.relative_to(source))
                    if not self._included(relative, path, filters):
                        excluded += 1
                        continue
                    info = path.stat()
                except OSError as exc:
                    raise FileBackupError(
                        "FILE_BACKUP_SCAN_FAILED",
                        f"No fue posible inspeccionar {path.name}",
                    ) from exc
                files.append(
                    ScannedFile(
                        source_index,
                        source,
                        relative,
                        path,
                        int(info.st_size),
                        int(info.st_mtime_ns),
                    )
                )
                if len(files) % 500 == 0:
                    progress(
                        {
                            "phase": "scanning",
                            "processedUnits": len(files),
                            "totalUnits": 0,
                            "foundCount": len(files),
                            "details": {"bytesFound": sum(item.size for item in files)},
                        }
                    )
        files.sort(key=lambda item: item.key)
        return files, excluded

    def _task_state(self, task_id: str) -> sqlite3.Row | None:
        with self.catalog.connect() as db:
            return db.execute(
                "SELECT * FROM task_state WHERE task_id = ?", (task_id,)
            ).fetchone()

    def _select_changes(
        self, task_id: str, strategy: str, files: list[ScannedFile]
    ) -> tuple[str, list[ScannedFile], list[str], str]:
        state = self._task_state(task_id)
        effective = strategy if state and state["last_full_run_id"] else "full"
        chain_id = str(state["last_chain_id"]) if state and effective != "full" else ""
        if effective == "full":
            return effective, files, [], chain_id
        with self.catalog.connect() as db:
            rows = db.execute(
                "SELECT * FROM catalog_entries WHERE task_id = ?", (task_id,)
            ).fetchall()
        previous = {str(row["file_key"]): row for row in rows if not row["deleted"]}
        current_keys = {item.key for item in files}
        selected: list[ScannedFile] = []
        for item in files:
            old = previous.get(item.key)
            if old is None:
                selected.append(item)
                continue
            if effective == "differential":
                size = old["full_size"]
                mtime = old["full_mtime_ns"]
            else:
                size = old["size"]
                mtime = old["mtime_ns"]
            if size is None or int(size) != item.size or int(mtime) != item.mtime_ns:
                selected.append(item)
        deleted = sorted(set(previous) - current_keys)
        return effective, selected, deleted, chain_id

    def simulate(
        self, payload: dict[str, Any], *, progress: ProgressCallback
    ) -> dict[str, Any]:
        task_id, _run_id, strategy = self._validate_payload(payload)
        progress({"phase": "scanning", "processedUnits": 0, "totalUnits": 0, "foundCount": 0})
        files, excluded = self._scan(payload, progress)
        effective, selected, deleted, _chain_id = self._select_changes(
            task_id, strategy, files
        )
        summary = {
            "requestedStrategy": strategy,
            "effectiveStrategy": effective,
            "filesScanned": len(files) + excluded,
            "filesTotal": len(selected),
            "bytesTotal": sum(item.size for item in selected),
            "excludedCount": excluded,
            "deletedCount": len(deleted),
            "warnings": [],
        }
        simulation_hash = hashlib.sha256(_canonical(summary)).hexdigest()
        progress(
            {
                "phase": "completed",
                "processedUnits": len(selected),
                "totalUnits": len(selected),
                "foundCount": len(files),
            }
        )
        return {
            "status": "completed",
            "taskId": task_id,
            "simulationHash": simulation_hash,
            "summary": summary,
        }

    def run(self, payload: dict[str, Any], *, progress: ProgressCallback) -> dict[str, Any]:
        task_id, run_id, strategy = self._validate_payload(payload)
        destination_root = self._destination_root(payload)
        task_name = _safe_label(str(payload.get("taskName") or task_id))
        progress({"phase": "preflight", "processedUnits": 0, "totalUnits": 0, "foundCount": 0})
        try:
            destination_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise FileBackupError(
                "FILE_BACKUP_DESTINATION_UNAVAILABLE",
                "No fue posible preparar el destino",
            ) from exc
        files, excluded = self._scan(payload, progress)
        effective, selected, deleted, chain_id = self._select_changes(
            task_id, strategy, files
        )
        if not chain_id:
            chain_id = run_id
        bytes_total = sum(item.size for item in selected)
        reserve = int((payload.get("storageThresholds") or {}).get("criticalFreeBytes") or 10 * 1024**3)
        try:
            free = int(self.disk_usage(destination_root).free)
        except OSError as exc:
            raise FileBackupError(
                "FILE_BACKUP_DESTINATION_UNAVAILABLE",
                "No fue posible consultar el espacio del destino",
            ) from exc
        if free - bytes_total < reserve:
            raise FileBackupError(
                "FILE_BACKUP_SPACE_INSUFFICIENT",
                f"Espacio insuficiente (libre={free}, requerido={bytes_total}, reserva={reserve})",
            )
        timestamp = self.now().strftime("%Y-%m-%d_%H%M%S")
        artifact_name = f"{timestamp}_{effective.upper()}"
        task_root = destination_root / task_name
        final_root = task_root / artifact_name
        partial_root = task_root / f".{artifact_name}.{run_id}.partial"
        with self.catalog.connect() as db:
            existing = db.execute(
                "SELECT * FROM local_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if existing:
                artifact_name = str(existing["artifact_name"])
                final_root = task_root / artifact_name
                partial_root = task_root / f".{artifact_name}.{run_id}.partial"
            else:
                if final_root.exists():
                    raise FileBackupError(
                        "FILE_BACKUP_ARTIFACT_CONFLICT",
                        "Ya existe una copia con el mismo nombre visible",
                    )
                now_text = self.now().isoformat()
                db.execute(
                    "INSERT INTO local_runs(run_id, task_id, strategy, chain_id, artifact_name, status, created_at, updated_at) VALUES(?,?,?,?,?,'running',?,?)",
                    (run_id, task_id, effective, chain_id, artifact_name, now_text, now_text),
                )
        if final_root.exists():
            raise FileBackupError(
                "FILE_BACKUP_ARTIFACT_CONFLICT",
                "La ejecución ya fue publicada y no puede sobrescribirse",
            )
        partial_root.mkdir(parents=True, exist_ok=True)
        manifest_files: list[dict[str, Any]] = []
        bytes_processed = 0
        for index, item in enumerate(selected, start=1):
            target = partial_root / item.archive_path
            checkpoint = self._checkpoint(run_id, item.key)
            if checkpoint and target.is_file():
                try:
                    if target.stat().st_size == int(checkpoint["size"]) and _sha256(target) == checkpoint["sha256"]:
                        digest = str(checkpoint["sha256"])
                        bytes_processed += item.size
                        manifest_files.append(self._manifest_file(item, digest))
                        continue
                except OSError:
                    pass
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".part")
            digest = hashlib.sha256()
            try:
                with item.path.open("rb") as source_stream, temporary.open("wb") as target_stream:
                    for chunk in iter(lambda: source_stream.read(1024 * 1024), b""):
                        target_stream.write(chunk)
                        digest.update(chunk)
                os.replace(temporary, target)
                source_info = item.path.stat()
                if source_info.st_size != item.size or source_info.st_mtime_ns != item.mtime_ns:
                    raise FileBackupError(
                        "FILE_BACKUP_SOURCE_CHANGED",
                        f"El archivo {item.path.name} cambió durante la copia",
                    )
                source_hash = digest.hexdigest()
                if target.stat().st_size != item.size or _sha256(target) != source_hash:
                    raise FileBackupError(
                        "FILE_BACKUP_VERIFY_FAILED",
                        f"La copia de {item.path.name} no superó la verificación",
                    )
            finally:
                temporary.unlink(missing_ok=True)
            self._save_checkpoint(run_id, item, target, source_hash)
            manifest_files.append(self._manifest_file(item, source_hash))
            bytes_processed += item.size
            progress(
                {
                    "phase": "copying",
                    "processedUnits": index,
                    "totalUnits": len(selected),
                    "foundCount": len(files),
                    "details": {
                        "bytesProcessed": bytes_processed,
                        "bytesTotal": bytes_total,
                        "currentFile": item.relative_path,
                    },
                }
            )
        progress(
            {
                "phase": "publishing",
                "processedUnits": len(selected),
                "totalUnits": len(selected),
                "foundCount": len(files),
            }
        )
        manifest = {
            "version": 1,
            "taskId": task_id,
            "taskName": str(payload.get("taskName") or task_id),
            "runId": run_id,
            "chainId": chain_id,
            "configRevision": int(payload.get("configRevision") or 0),
            "requestedStrategy": strategy,
            "strategy": effective,
            "createdAt": self.now().isoformat(),
            "sources": [dict(item) for item in payload.get("sources") or []],
            "files": manifest_files,
            "deleted": deleted,
            "summary": {
                "filesScanned": len(files) + excluded,
                "filesCopied": len(selected),
                "bytesCopied": bytes_processed,
                "excludedCount": excluded,
                "deletedCount": len(deleted),
            },
        }
        manifest_path = partial_root / "manifest.json"
        manifest_path.write_bytes(_canonical(manifest))
        manifest_hash = _sha256(manifest_path)
        try:
            os.rename(partial_root, final_root)
        except OSError as exc:
            raise FileBackupError(
                "FILE_BACKUP_PUBLISH_FAILED", "No fue posible publicar la copia"
            ) from exc
        self._commit_catalog(task_id, run_id, chain_id, effective, files, manifest_files)
        with self.catalog.connect() as db:
            db.execute(
                "UPDATE local_runs SET status='completed', manifest_path=?, updated_at=? WHERE run_id=?",
                (str(final_root / "manifest.json"), self.now().isoformat(), run_id),
            )
        progress(
            {
                "phase": "completed",
                "processedUnits": len(selected),
                "totalUnits": len(selected),
                "foundCount": len(files),
                "details": {"bytesProcessed": bytes_processed},
            }
        )
        return {
            "status": "completed",
            "taskId": task_id,
            "fileRunId": run_id,
            "chainId": chain_id,
            "requestedStrategy": strategy,
            "effectiveStrategy": effective,
            "summary": manifest["summary"],
            "artifact": {
                "kind": "directory",
                "location": str(final_root),
                "sizeBytes": bytes_processed,
                "manifestRef": str(final_root / "manifest.json"),
                "manifestSha256": manifest_hash,
            },
            "checkpointRef": str(self.catalog.path),
            "catalogRevision": self.catalog_revision,
        }

    @staticmethod
    def _manifest_file(item: ScannedFile, digest: str) -> dict[str, Any]:
        return {
            "sourceIndex": item.source_index,
            "sourcePath": str(item.source_path),
            "relativePath": item.relative_path,
            "archivePath": str(item.archive_path),
            "sizeBytes": item.size,
            "modifiedNs": item.mtime_ns,
            "sha256": digest,
        }

    def _checkpoint(self, run_id: str, file_key: str) -> sqlite3.Row | None:
        with self.catalog.connect() as db:
            return db.execute(
                "SELECT * FROM checkpoints WHERE run_id=? AND file_key=?",
                (run_id, file_key),
            ).fetchone()

    def _save_checkpoint(
        self, run_id: str, item: ScannedFile, target: Path, digest: str
    ) -> None:
        with self.catalog.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO checkpoints(run_id,file_key,destination_path,size,sha256) VALUES(?,?,?,?,?)",
                (run_id, item.key, str(target), item.size, digest),
            )

    def _commit_catalog(
        self,
        task_id: str,
        run_id: str,
        chain_id: str,
        strategy: str,
        files: list[ScannedFile],
        manifest_files: list[dict[str, Any]],
    ) -> None:
        digests = {
            f"{int(item['sourceIndex'])}:{str(item['relativePath']).casefold()}": str(item["sha256"])
            for item in manifest_files
        }
        with self.catalog.connect() as db:
            previous_rows = db.execute(
                "SELECT file_key, sha256 FROM catalog_entries WHERE task_id=?", (task_id,)
            ).fetchall()
            previous_hashes = {str(row["file_key"]): str(row["sha256"]) for row in previous_rows}
            current_keys = {item.key for item in files}
            for item in files:
                digest = digests.get(item.key) or previous_hashes.get(item.key)
                if not digest:
                    digest = _sha256(item.path)
                if strategy == "full":
                    full_values = (item.size, item.mtime_ns, digest)
                else:
                    old = db.execute(
                        "SELECT full_size, full_mtime_ns, full_sha256 FROM catalog_entries WHERE task_id=? AND file_key=?",
                        (task_id, item.key),
                    ).fetchone()
                    full_values = (
                        old["full_size"] if old else None,
                        old["full_mtime_ns"] if old else None,
                        old["full_sha256"] if old else None,
                    )
                db.execute(
                    """
                    INSERT OR REPLACE INTO catalog_entries(
                        task_id,file_key,source_index,relative_path,size,mtime_ns,sha256,
                        full_size,full_mtime_ns,full_sha256,last_run_id,deleted
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,0)
                    """,
                    (
                        task_id,
                        item.key,
                        item.source_index,
                        item.relative_path,
                        item.size,
                        item.mtime_ns,
                        digest,
                        *full_values,
                        run_id,
                    ),
                )
            for file_key in set(previous_hashes) - current_keys:
                db.execute(
                    "UPDATE catalog_entries SET deleted=1,last_run_id=? WHERE task_id=? AND file_key=?",
                    (run_id, task_id, file_key),
                )
            now_text = self.now().isoformat()
            last_full = run_id if strategy == "full" else None
            old_state = db.execute(
                "SELECT last_full_run_id FROM task_state WHERE task_id=?", (task_id,)
            ).fetchone()
            if last_full is None and old_state:
                last_full = old_state["last_full_run_id"]
            db.execute(
                "INSERT OR REPLACE INTO task_state(task_id,last_run_id,last_full_run_id,last_chain_id,updated_at) VALUES(?,?,?,?,?)",
                (task_id, run_id, last_full, chain_id, now_text),
            )
            revision_row = db.execute(
                "SELECT value FROM metadata WHERE key='catalog_revision'"
            ).fetchone()
            revision = int(revision_row["value"] if revision_row else 0) + 1
            db.execute(
                "UPDATE metadata SET value=? WHERE key='catalog_revision'",
                (str(revision),),
            )

    def test_destination(
        self, payload: dict[str, Any], *, progress: ProgressCallback
    ) -> dict[str, Any]:
        root = self._destination_root(payload)
        root.mkdir(parents=True, exist_ok=True)
        probe = root / f".dataexpress-file-backup-probe-{os.getpid()}"
        renamed = probe.with_suffix(".verified")
        content = os.urandom(64)
        try:
            probe.write_bytes(content)
            if hashlib.sha256(probe.read_bytes()).digest() != hashlib.sha256(content).digest():
                raise OSError
            os.replace(probe, renamed)
            renamed.unlink()
        except OSError as exc:
            raise FileBackupError(
                "FILE_BACKUP_DESTINATION_TEST_FAILED",
                "El destino no permite escribir, leer, renombrar y eliminar",
            ) from exc
        return {
            "status": "completed",
            "operations": ["write", "read", "hash", "rename", "delete"],
        }
