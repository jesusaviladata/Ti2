from __future__ import annotations

import ctypes
import os
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any


class ExplorerError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_REPARSE_POINT = 0x400


def _is_reparse_point(path: Path) -> bool:
    try:
        stat = path.lstat()
    except OSError:
        return True
    return bool(getattr(stat, "st_file_attributes", 0) & _REPARSE_POINT) or path.is_symlink()


def _safe_target_name(value: str) -> str:
    name = value.strip()
    if (
        not name
        or name in {".", ".."}
        or any(character in name for character in ("/", "\\", ":", "\x00"))
        or name.casefold() in {"core", "web"}
        or len(name) > 255
    ):
        raise ExplorerError("TARGET_NAME_INVALID", "Un objetivo configurado no es válido")
    return name


def _safe_directory(path_value: str) -> Path:
    if not path_value or path_value.startswith(("\\\\", "//", "\\\\?\\", "\\\\.\\")):
        raise ExplorerError("PATH_INVALID", "La ruta no es válida")
    if os.name == "nt" and not _WINDOWS_ABSOLUTE.match(path_value):
        raise ExplorerError("PATH_INVALID", "La ruta debe ser absoluta")
    path = Path(path_value)
    if not path.is_absolute():
        raise ExplorerError("PATH_INVALID", "La ruta debe ser absoluta")
    if any(part == ".." for part in path.parts):
        raise ExplorerError("PATH_INVALID", "La ruta no es válida")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ExplorerError("PATH_NOT_FOUND", "La carpeta no existe") from exc
    if not resolved.is_dir() or _is_reparse_point(resolved):
        raise ExplorerError("PATH_INVALID", "La ruta no es una carpeta permitida")
    return resolved


def _windows_drives() -> Iterable[str]:
    if os.name != "nt":
        return []
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    if not mask:
        raise ExplorerError("DRIVE_ENUMERATION_FAILED", "No se pudieron enumerar los discos")
    return [f"{chr(65 + index)}:\\" for index in range(26) if mask & (1 << index)]


class WindowsExplorer:
    def __init__(
        self,
        *,
        drive_provider: Callable[[], Iterable[str]] | None = None,
        max_entries: int = 5000,
        max_validation_seconds: int = 120,
    ):
        self.drive_provider = drive_provider or _windows_drives
        self.max_entries = max_entries
        self.max_validation_seconds = max_validation_seconds

    def browse_drives(self) -> dict[str, Any]:
        drives = []
        for value in self.drive_provider():
            try:
                readable = os.access(value, os.R_OK)
            except OSError:
                readable = False
            drives.append({"path": value, "label": value[:2], "readable": readable})
        return {"drives": drives}

    def browse_directory(self, path_value: str) -> dict[str, Any]:
        root = _safe_directory(path_value)
        entries: list[dict[str, str]] = []
        truncated = False
        try:
            with os.scandir(root) as iterator:
                for entry in iterator:
                    if len(entries) >= self.max_entries:
                        truncated = True
                        break
                    try:
                        if entry.is_dir(follow_symlinks=False) and not entry.is_symlink():
                            entries.append({"name": entry.name, "path": entry.path})
                    except OSError:
                        continue
        except PermissionError as exc:
            raise ExplorerError("PATH_ACCESS_DENIED", "No hay acceso a la carpeta") from exc
        entries.sort(key=lambda item: item["name"].casefold())
        return {"path": str(root), "directories": entries, "truncated": truncated}

    def validate_structure(
        self,
        root_value: str,
        *,
        target_folders: list[str],
        target_files: list[str],
        progress: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        root = _safe_directory(root_value)
        folders = [_safe_target_name(value) for value in target_folders]
        files = [_safe_target_name(value) for value in target_files]
        folder_counts = {name: 0 for name in folders}
        file_counts = {name: 0 for name in files}
        errors: list[dict[str, str]] = []
        properties: list[Path] = []
        truncated = False
        try:
            with os.scandir(root) as iterator:
                for entry in iterator:
                    if len(properties) >= self.max_entries:
                        truncated = True
                        break
                    if entry.name.casefold() in {".dataexpress-quarantine"}:
                        continue
                    try:
                        path = Path(entry.path)
                        if entry.is_dir(follow_symlinks=False) and not _is_reparse_point(path):
                            properties.append(path)
                    except OSError:
                        errors.append({"property": entry.name, "code": "PROPERTY_INACCESSIBLE"})
        except PermissionError as exc:
            raise ExplorerError("ROOT_ACCESS_DENIED", "No hay acceso a la raíz") from exc

        properties.sort(key=lambda path: path.name.casefold())
        with_core = 0
        without_core = 0
        with_web = 0
        processed = 0
        for property_path in properties:
            if time.monotonic() - started > self.max_validation_seconds:
                truncated = True
                break
            try:
                children = {
                    entry.name.casefold(): entry
                    for entry in os.scandir(property_path)
                    if entry.is_dir(follow_symlinks=False) and not entry.is_symlink()
                }
                if "web" in children:
                    with_web += 1
                core_entry = children.get("core")
                if core_entry is None or _is_reparse_point(Path(core_entry.path)):
                    without_core += 1
                else:
                    with_core += 1
                    core_children = {
                        entry.name.casefold(): entry
                        for entry in os.scandir(core_entry.path)
                        if not entry.is_symlink()
                    }
                    for name in folders:
                        entry = core_children.get(name.casefold())
                        if entry is not None and entry.is_dir(follow_symlinks=False):
                            folder_counts[name] += 1
                    for name in files:
                        entry = core_children.get(name.casefold())
                        if entry is not None and entry.is_file(follow_symlinks=False):
                            file_counts[name] += 1
            except PermissionError:
                errors.append({"property": property_path.name, "code": "PROPERTY_ACCESS_DENIED"})
            except OSError:
                errors.append({"property": property_path.name, "code": "PROPERTY_READ_FAILED"})
            processed += 1
            if progress:
                progress(processed, len(properties))

        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "valid": bool(properties) and processed > 0,
            "root": str(root),
            "propertiesDetected": len(properties),
            "propertiesProcessed": processed,
            "propertiesWithCore": with_core,
            "propertiesWithoutCore": without_core,
            "propertiesWithWeb": with_web,
            "targetFolders": folder_counts,
            "targetFiles": file_counts,
            "errors": errors[:100],
            "errorCount": len(errors),
            "truncated": truncated,
            "durationMs": duration_ms,
        }

