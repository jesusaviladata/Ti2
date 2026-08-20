from __future__ import annotations

import getpass
import platform
from typing import Any


def discover_environment(sql_profiles: tuple[dict, ...], destination_profiles: tuple[dict, ...]) -> dict[str, Any]:
    return {
        "hostname": platform.node(),
        "os": platform.platform(),
        "serviceAccount": getpass.getuser(),
        "sqlCandidates": [
            {"server": item.get("server", ""), "label": item.get("label", "")}
            for item in sql_profiles
        ],
        "destinationCandidates": [
            {"type": item.get("type", ""), "path": item.get("path", ""), "label": item.get("label", "")}
            for item in destination_profiles
        ],
        "recommendedAuthentication": "windows_integrated",
    }
