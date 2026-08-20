from __future__ import annotations

import ctypes
import ntpath
import shutil
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def volume_root(path_value: str) -> str:
    value = str(path_value).strip()
    drive, _tail = ntpath.splitdrive(value)
    if drive:
        return drive + "\\"
    anchor = Path(value).anchor
    return anchor or value


def windows_volume_label(root: str) -> str:
    if not root:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(261)
        success = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root),
            buffer,
            len(buffer),
            None,
            None,
            None,
            None,
            0,
        )
        return buffer.value if success else ""
    except (AttributeError, OSError):
        return ""


class StorageCollector:
    def __init__(
        self,
        roots: Iterable[tuple[str, str]],
        *,
        disk_usage: Callable[[str], Any] = shutil.disk_usage,
        label_provider: Callable[[str], str] = windows_volume_label,
        now: Callable[[], datetime] | None = None,
    ):
        root_items = list(roots)
        grouped: dict[str, set[str]] = {}
        for path, role in root_items:
            root = volume_root(path)
            if root:
                grouped.setdefault(root.casefold(), set()).add(role)
        self.roots = {
            key: {"mountPoint": volume_root(next(path for path, _role in root_items if volume_root(path).casefold() == key)), "roles": roles}
            for key, roles in grouped.items()
        }
        self.disk_usage = disk_usage
        self.label_provider = label_provider
        self.now = now or (lambda: datetime.now(timezone.utc))

    @classmethod
    def from_profiles(
        cls,
        sql_profiles: tuple[dict, ...],
        destination_profiles: tuple[dict, ...],
        cleanup_roots: tuple[str, ...] = (),
    ) -> "StorageCollector":
        roots: list[tuple[str, str]] = []
        roots.extend(
            (str(profile.get("backupRoot") or "D:\\"), "backup")
            for profile in sql_profiles
        )
        roots.extend(
            (str(profile.get("path") or ""), "destination")
            for profile in destination_profiles
            if str(profile.get("path") or "").strip()
        )
        roots.extend((root, "cleanup") for root in cleanup_roots)
        return cls(roots)

    def collect(self) -> list[dict[str, Any]]:
        observed_at = self.now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        items = []
        for item in self.roots.values():
            mount_point = item["mountPoint"]
            payload = {
                "volumeKey": mount_point.rstrip("\\/") or mount_point,
                "label": self.label_provider(mount_point)[:255],
                "mountPoint": mount_point,
                "totalBytes": None,
                "freeBytes": None,
                "usedPercent": None,
                "roles": sorted(item["roles"]),
                "observedAt": observed_at,
                "error": None,
            }
            try:
                usage = self.disk_usage(mount_point)
                payload["totalBytes"] = int(usage.total)
                payload["freeBytes"] = int(usage.free)
                payload["usedPercent"] = (
                    round(int(usage.used) / int(usage.total) * 100, 2)
                    if int(usage.total) > 0
                    else None
                )
            except (OSError, ValueError):
                payload["error"] = "No se pudo leer el volumen"
            items.append(payload)
        return items
