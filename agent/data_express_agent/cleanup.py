from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .explorer import _is_reparse_point, _safe_directory, _safe_target_name


ProgressCallback = Callable[[dict[str, Any]], None]
_SAFE_CONTAINER = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_PROTECTED_EXTENSIONS = {
    ".bak",
    ".trn",
    ".zip",
    ".rar",
    ".7z",
    ".exe",
    ".dll",
    ".key",
    ".pem",
    ".pfx",
    ".config",
}


class CleanupError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_container(value: str) -> str:
    name = value.strip()
    if not _SAFE_CONTAINER.fullmatch(name) or name in {".", ".."}:
        raise CleanupError("CONTAINER_INVALID", "La carpeta contenedora no es valida")
    return name


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError, RuntimeError):
        return False


class StructuralCleanupExecutor:
    def __init__(
        self,
        data_dir: Path,
        *,
        now: Callable[[], datetime] | None = None,
        simulation_ttl_minutes: int = 30,
        max_candidates: int = 200_000,
    ):
        self.data_dir = data_dir
        self.simulations_dir = data_dir / "simulations"
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.simulation_ttl_minutes = simulation_ttl_minutes
        self.max_candidates = max_candidates

    def simulate(
        self,
        payload: dict[str, Any],
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        root = _safe_directory(str(payload["root"]))
        if root.parent == root:
            raise CleanupError("ROOT_TOO_BROAD", "No se permite limpiar la raiz del sistema")
        container = _safe_container(str(payload.get("containerFolder") or "Core"))
        target_folders = [_safe_target_name(str(item)) for item in payload.get("targetFolders", [])]
        target_files = [_safe_target_name(str(item)) for item in payload.get("targetFiles", [])]
        if not target_folders and not target_files:
            raise CleanupError("CLEANUP_TARGET_REQUIRED", "Defina al menos un objetivo de limpieza")
        max_properties = max(0, int(payload.get("maxProperties") or 0))
        max_files = max(0, int(payload.get("maxFiles") or 0))
        max_bytes = max(0, int(payload.get("maxBytes") or 0))
        candidates: list[dict[str, Any]] = []
        protected: list[dict[str, str]] = []
        properties = []
        with os.scandir(root) as entries:
            for entry in entries:
                path = Path(entry.path)
                if entry.name.casefold() == ".dataexpress-quarantine":
                    continue
                if entry.is_dir(follow_symlinks=False) and not _is_reparse_point(path):
                    properties.append(path)
        properties.sort(key=lambda value: value.name.casefold())
        if max_properties:
            properties = properties[:max_properties]

        for index, property_path in enumerate(properties, start=1):
            core = property_path / container
            if core.is_dir() and not _is_reparse_point(core):
                for folder_name in target_folders:
                    folder = core / folder_name
                    if folder.is_dir() and not _is_reparse_point(folder):
                        self._collect_files(folder, root, candidates, protected)
                for file_name in target_files:
                    file_path = core / file_name
                    if file_path.is_file() and not file_path.is_symlink():
                        self._append_candidate(file_path, root, candidates, protected)
            if progress and (index == len(properties) or index % 25 == 0):
                progress(
                    {
                        "phase": "simulating_cleanup",
                        "processedUnits": index,
                        "totalUnits": len(properties),
                        "foundCount": len(candidates),
                    }
                )
            if len(candidates) >= self.max_candidates:
                break

        limited = False
        if max_files and len(candidates) > max_files:
            candidates = candidates[:max_files]
            limited = True
        if max_bytes:
            selected: list[dict[str, Any]] = []
            selected_bytes = 0
            for item in candidates:
                item_bytes = int(item["sizeBytes"])
                if selected and selected_bytes + item_bytes > max_bytes:
                    limited = True
                    break
                selected.append(item)
                selected_bytes += item_bytes
            if len(selected) < len(candidates):
                limited = True
            candidates = selected

        simulation_id = str(uuid.uuid4())
        created_at = self.now()
        expires_at = created_at + timedelta(minutes=self.simulation_ttl_minutes)
        manifest = {
            "version": 1,
            "simulationId": simulation_id,
            "createdAt": created_at.isoformat(),
            "expiresAt": expires_at.isoformat(),
            "root": str(root),
            "containerFolder": container,
            "targetFolders": target_folders,
            "targetFiles": target_files,
            "candidates": candidates,
        }
        manifest_hash = hashlib.sha256(_canonical(manifest)).hexdigest()
        document = {"manifest": manifest, "manifestHash": manifest_hash}
        self.simulations_dir.mkdir(parents=True, exist_ok=True)
        path = self.simulations_dir / f"{simulation_id}.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_bytes(_canonical(document))
        os.replace(temporary, path)
        by_property: dict[str, int] = {}
        for item in candidates:
            property_name = Path(str(item["relativePath"])).parts[0]
            by_property[property_name] = by_property.get(property_name, 0) + 1
        return {
            "simulationId": simulation_id,
            "manifestHash": manifest_hash,
            "expiresAt": expires_at.isoformat(),
            "root": str(root),
            "propertiesProcessed": len(properties),
            "propertiesAffected": len(by_property),
            "byProperty": by_property,
            "eligibleCount": len(candidates),
            "bytesEligible": sum(int(item["sizeBytes"]) for item in candidates),
            "protectedCount": len(protected),
            "samples": candidates[:100],
            "protected": protected[:100],
            "truncated": len(candidates) >= self.max_candidates or limited,
        }

    def execute_direct(
        self,
        payload: dict[str, Any],
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Delete exactly the unchanged files captured by a valid simulation."""
        simulation_id = str(payload["simulationId"])
        expected_hash = str(payload["manifestHash"])
        manifest = self._load_manifest(simulation_id, expected_hash)
        root = _safe_directory(str(manifest["root"]))
        deleted: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        candidates = list(manifest["candidates"])

        for index, item in enumerate(candidates, start=1):
            source = Path(str(item["path"]))
            relative = Path(str(item["relativePath"]))
            try:
                if not _inside(source, root) or not source.is_file() or source.is_symlink():
                    raise OSError("source changed")
                stat = source.stat()
                if stat.st_size != int(item["sizeBytes"]) or stat.st_mtime_ns != int(item["mtimeNs"]):
                    raise OSError("source changed")
                source.unlink()
                deleted.append(
                    {
                        "relativePath": str(relative),
                        "sizeBytes": int(item["sizeBytes"]),
                    }
                )
            except OSError:
                errors.append({"relativePath": str(relative), "code": "FILE_CHANGED_OR_INACCESSIBLE"})
            if progress and (index == len(candidates) or index % 25 == 0):
                progress(
                    {
                        "phase": "deleting_logs",
                        "processedUnits": index,
                        "totalUnits": len(candidates),
                        "foundCount": len(deleted),
                    }
                )

        return {
            "deletedCount": len(deleted),
            "bytesDeleted": sum(int(item["sizeBytes"]) for item in deleted),
            "failedCount": len(errors),
            "errors": errors[:100],
            "root": str(root),
        }

    def execute_quarantine(
        self,
        payload: dict[str, Any],
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        simulation_id = str(payload["simulationId"])
        expected_hash = str(payload["manifestHash"])
        manifest = self._load_manifest(simulation_id, expected_hash)
        root = _safe_directory(str(manifest["root"]))
        execution_id = str(payload.get("executionId") or uuid.uuid4())
        if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", execution_id):
            raise CleanupError("EXECUTION_ID_INVALID", "El identificador de ejecucion no es valido")
        quarantine_root = root / ".dataexpress-quarantine" / execution_id
        moved: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        candidates = list(manifest["candidates"])
        for index, item in enumerate(candidates, start=1):
            source = Path(str(item["path"]))
            relative = Path(str(item["relativePath"]))
            destination = quarantine_root / relative
            try:
                if not _inside(source, root) or not source.is_file() or source.is_symlink():
                    raise OSError("source changed")
                stat = source.stat()
                if stat.st_size != int(item["sizeBytes"]) or stat.st_mtime_ns != int(item["mtimeNs"]):
                    raise OSError("source changed")
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, destination)
                moved.append(
                    {
                        "relativePath": str(relative),
                        "sizeBytes": int(item["sizeBytes"]),
                    }
                )
            except OSError:
                errors.append({"relativePath": str(relative), "code": "FILE_CHANGED_OR_INACCESSIBLE"})
            if progress and (index == len(candidates) or index % 25 == 0):
                progress(
                    {
                        "phase": "moving_to_quarantine",
                        "processedUnits": index,
                        "totalUnits": len(candidates),
                        "foundCount": len(moved),
                    }
                )
        execution_manifest = {
            "version": 1,
            "executionId": execution_id,
            "root": str(root),
            "quarantineRoot": str(quarantine_root),
            "createdAt": self.now().isoformat(),
            "items": moved,
        }
        quarantine_root.mkdir(parents=True, exist_ok=True)
        (quarantine_root / "manifest.json").write_bytes(_canonical(execution_manifest))
        return {
            "executionId": execution_id,
            "movedCount": len(moved),
            "bytesMoved": sum(int(item["sizeBytes"]) for item in moved),
            "failedCount": len(errors),
            "errors": errors[:100],
            "quarantineRoot": str(quarantine_root),
        }

    def restore(self, payload: dict[str, Any]) -> dict[str, Any]:
        root = _safe_directory(str(payload["root"]))
        execution_id = str(payload["executionId"])
        quarantine_root = root / ".dataexpress-quarantine" / execution_id
        manifest = self._load_execution_manifest(quarantine_root)
        requested = str(payload.get("relativePath") or "").strip()
        items = [item for item in manifest["items"] if not requested or item["relativePath"] == requested]
        restored = 0
        errors: list[dict[str, str]] = []
        for item in items:
            relative = Path(str(item["relativePath"]))
            source = quarantine_root / relative
            destination = root / relative
            try:
                if not _inside(source, quarantine_root) or not source.is_file() or destination.exists():
                    raise OSError("restore conflict")
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, destination)
                restored += 1
            except OSError:
                errors.append({"relativePath": str(relative), "code": "RESTORE_CONFLICT"})
        return {"executionId": execution_id, "restoredCount": restored, "failedCount": len(errors), "errors": errors[:100]}

    def purge(self, payload: dict[str, Any]) -> dict[str, Any]:
        root = _safe_directory(str(payload["root"]))
        execution_id = str(payload["executionId"])
        quarantine_base = root / ".dataexpress-quarantine"
        quarantine_root = quarantine_base / execution_id
        self._load_execution_manifest(quarantine_root)
        if not _inside(quarantine_root, quarantine_base):
            raise CleanupError("QUARANTINE_PATH_INVALID", "La cuarentena no es valida")
        shutil.rmtree(quarantine_root)
        return {"executionId": execution_id, "purged": True}

    def _collect_files(
        self,
        folder: Path,
        root: Path,
        candidates: list[dict[str, Any]],
        protected: list[dict[str, str]],
    ) -> None:
        for current, directory_names, file_names in os.walk(folder, followlinks=False):
            current_path = Path(current)
            directory_names[:] = [
                name
                for name in sorted(directory_names, key=str.casefold)
                if not _is_reparse_point(current_path / name)
            ]
            for file_name in sorted(file_names, key=str.casefold):
                self._append_candidate(current_path / file_name, root, candidates, protected)
                if len(candidates) >= self.max_candidates:
                    return

    @staticmethod
    def _append_candidate(
        path: Path,
        root: Path,
        candidates: list[dict[str, Any]],
        protected: list[dict[str, str]],
    ) -> None:
        if path.is_symlink() or not _inside(path, root):
            return
        if path.suffix.casefold() in _PROTECTED_EXTENSIONS:
            protected.append({"path": str(path), "reason": "protected_extension"})
            return
        try:
            stat = path.stat()
        except OSError:
            return
        candidates.append(
            {
                "path": str(path),
                "relativePath": str(path.relative_to(root)),
                "sizeBytes": int(stat.st_size),
                "mtimeNs": int(stat.st_mtime_ns),
            }
        )

    def _load_manifest(self, simulation_id: str, expected_hash: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", simulation_id):
            raise CleanupError("SIMULATION_ID_INVALID", "La simulacion no es valida")
        try:
            document = json.loads((self.simulations_dir / f"{simulation_id}.json").read_text(encoding="utf-8"))
            manifest = document["manifest"]
            actual_hash = hashlib.sha256(_canonical(manifest)).hexdigest()
            expires_at = datetime.fromisoformat(manifest["expiresAt"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CleanupError("SIMULATION_NOT_FOUND", "La simulacion local no existe") from exc
        if actual_hash != expected_hash or document.get("manifestHash") != expected_hash:
            raise CleanupError("SIMULATION_TAMPERED", "La simulacion no coincide con el manifiesto")
        if expires_at <= self.now():
            raise CleanupError("SIMULATION_EXPIRED", "La simulacion expiro; ejecute una nueva")
        return manifest

    @staticmethod
    def _load_execution_manifest(quarantine_root: Path) -> dict[str, Any]:
        try:
            document = json.loads((quarantine_root / "manifest.json").read_text(encoding="utf-8"))
            if document.get("version") != 1 or Path(document["quarantineRoot"]) != quarantine_root:
                raise ValueError
            return document
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CleanupError("QUARANTINE_NOT_FOUND", "La cuarentena no existe") from exc
