from __future__ import annotations

from app.models.backup import Backup


def serialize_backup(item: Backup) -> dict:
    duration = None
    if item.started_at and item.finished_at:
        duration = int((item.finished_at - item.started_at).total_seconds())
    return {
        "id": str(item.id),
        "tenantId": str(item.tenant_id),
        "databaseName": item.database_name,
        "backupType": item.backup_type.value,
        "status": item.status.value,
        "destination": item.destination.value,
        "filePath": item.file_path,
        "fileSizeBytes": item.file_size_bytes,
        "sha256Hash": item.sha256_hash,
        "errorMessage": item.error_message,
        "agentId": str(item.agent_id) if item.agent_id else None,
        "runId": item.run_id,
        "phase": item.phase,
        "progressPercent": item.progress_percent,
        "validationMethod": item.validation_method,
        "triggerReason": item.trigger_reason,
        "deliveryStatus": item.delivery_status,
        "deliveryPhase": item.delivery_phase,
        "deliveryProgress": item.delivery_progress,
        "deliveryErrorMessage": item.delivery_error_message,
        "deliveryProfileId": item.delivery_profile_id,
        "archivePath": item.archive_path,
        "archiveSizeBytes": item.archive_size_bytes,
        "archiveSha256": item.archive_sha256,
        "origin": item.origin_snapshot,
        "startedAt": item.started_at.isoformat() if item.started_at else None,
        "finishedAt": item.finished_at.isoformat() if item.finished_at else None,
        "durationSecs": duration,
        "createdAt": item.created_at.isoformat(),
    }
