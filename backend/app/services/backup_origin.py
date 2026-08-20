from __future__ import annotations

from typing import Any

from app.models.operations import RemoteAgent


def _public_profile(metadata: dict, field: str, profile_id: str | None) -> dict | None:
    if not profile_id:
        return None
    for item in metadata.get(field, []) or []:
        if str(item.get("id") or "") == profile_id:
            result = {
                "id": profile_id,
                "label": str(item.get("label") or profile_id)[:128],
            }
            if field == "backupDestinations":
                result["type"] = str(item.get("type") or "")[:20]
            return result
    return {"id": profile_id, "label": profile_id}


def create_backup_origin_snapshot(
    agent: RemoteAgent,
    *,
    sql_profile_id: str,
    destination_profile_id: str | None,
) -> dict[str, Any]:
    metadata = agent.metadata_json or {}
    sql_profile = _public_profile(metadata, "sqlInstances", sql_profile_id)
    destination_profile = _public_profile(
        metadata, "backupDestinations", destination_profile_id
    )
    return {
        "agent": {
            "id": str(agent.id),
            "hostname": agent.hostname,
        },
        "sqlProfile": sql_profile,
        "destinationProfile": destination_profile,
        "sourceLabel": f"{agent.hostname} · {sql_profile['label']}",
    }
