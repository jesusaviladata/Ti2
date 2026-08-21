from __future__ import annotations

import getpass
import ntpath
import platform
import shutil
from typing import Any


def _volume_candidates(profiles: tuple[dict, ...]) -> list[dict[str, Any]]:
    roots: dict[str, str] = {}
    for profile in profiles:
        for key in ("backupRoot", "path"):
            value = str(profile.get(key) or "").strip()
            drive, _tail = ntpath.splitdrive(value)
            if drive:
                roots.setdefault(drive.casefold(), drive + "\\")
    volumes: list[dict[str, Any]] = []
    for root in roots.values():
        try:
            usage = shutil.disk_usage(root)
            volumes.append(
                {
                    "mountPoint": root,
                    "totalBytes": int(usage.total),
                    "freeBytes": int(usage.free),
                }
            )
        except OSError:
            volumes.append({"mountPoint": root, "totalBytes": None, "freeBytes": None})
    return volumes


def discover_environment(sql_profiles: tuple[dict, ...], destination_profiles: tuple[dict, ...]) -> dict[str, Any]:
    return {
        "hostname": platform.node(),
        "os": platform.platform(),
        "serviceAccount": getpass.getuser(),
        "sqlCandidates": [
            {
                "server": item.get("server", ""),
                "label": item.get("label", ""),
                "profileKey": item.get("profileKey", item.get("id", "")),
                "backupRoot": item.get("backupRoot", ""),
                "requiresSecret": bool(item.get("requiresSecret")),
            }
            for item in sql_profiles
        ],
        "destinationCandidates": [
            {
                "type": item.get("type", ""),
                "path": item.get("path", ""),
                "label": item.get("label", ""),
                "profileKey": item.get("profileKey", item.get("id", "")),
                "host": item.get("host", ""),
                "username": item.get("username", ""),
                "hasLocalPrivateKey": bool(item.get("privateKeyPath")),
                "requiresSecret": bool(item.get("requiresSecret")),
            }
            for item in destination_profiles
        ],
        "volumeCandidates": _volume_candidates(sql_profiles + destination_profiles),
        "recommendedAuthentication": "windows_integrated",
    }
