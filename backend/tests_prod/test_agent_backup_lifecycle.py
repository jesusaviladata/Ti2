import uuid
from datetime import datetime, timezone

import pytest

from app.models.backup import Backup, BackupDestination, BackupStatus, BackupType
from app.models.operations import AgentCommand
from app.services.agent_command_service import AgentCommandService


class FakeDb:
    async def flush(self):
        return None


class LifecycleService(AgentCommandService):
    def __init__(self, backups):
        super().__init__(FakeDb(), repo=None)
        self.backups = backups

    async def _backups_for_command(self, _command):
        return self.backups


def command(command_type="run_backup_batch"):
    return AgentCommand(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), agent_id=uuid.uuid4(),
        command_type=command_type, payload={"runId": "run-1"}, payload_hash="0" * 64,
        status="claimed", idempotency_key="run-1", expires_at=datetime.now(timezone.utc),
    )


def backup():
    return Backup(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), database_name="Ipsofactu",
        backup_type=BackupType.full, status=BackupStatus.running,
        destination=BackupDestination.nas, progress_percent=0, delivery_status="pending",
    )


@pytest.mark.asyncio
async def test_bak_becomes_ready_before_archive_and_delivery():
    item = backup()
    service = LifecycleService([item])

    await service._project_backup_progress(
        command(), phase="backup_ready", database="Ipsofactu",
        details={
            "fileName": "Ipsofactu_2026-08-20.bak", "fileSizeBytes": 128,
            "fileSha256": "a" * 64, "verificationMethod": "restore_verifyonly",
        }, processed_units=1, total_units=1,
    )

    assert item.status == BackupStatus.completed
    assert item.progress_percent == 100
    assert item.validation_method == "restore_verifyonly"
    assert item.delivery_status == "processing"


@pytest.mark.asyncio
async def test_delivery_failure_keeps_validated_backup_ready():
    item = backup()
    item.status = BackupStatus.completed
    item.progress_percent = 100
    service = LifecycleService([item])

    await service._project_backup_failure(command(), "SFTP interrumpido", datetime.now(timezone.utc))

    assert item.status == BackupStatus.completed
    assert item.progress_percent == 100
    assert item.delivery_status == "failed"
    assert item.delivery_error_message == "SFTP interrumpido"


@pytest.mark.asyncio
async def test_retry_completion_updates_only_delivery_lifecycle():
    item = backup()
    item.status = BackupStatus.completed
    item.progress_percent = 100
    item.delivery_status = "processing"
    service = LifecycleService([item])

    await service._project_backup_complete(
        command("retry_backup_delivery"),
        {"zipPath": "D:/backup.zip", "zipSizeBytes": 64, "zipSha256": "b" * 64,
         "transfer": {"path": "/remote/backup.zip", "verified": True}},
        datetime.now(timezone.utc),
    )

    assert item.status == BackupStatus.completed
    assert item.delivery_status == "delivered"
    assert item.delivery_progress == 100


@pytest.mark.asyncio
async def test_local_zip_is_ready_without_being_reported_as_remotely_delivered():
    item = backup()
    item.destination = BackupDestination.local
    service = LifecycleService([item])

    await service._project_backup_complete(
        command(),
        {
            "databases": [
                {
                    "databaseName": "Ipsofactu",
                    "fileName": "Ipsofactu_2026-08-20.bak",
                    "verificationMethod": "restore_verifyonly",
                }
            ],
            "zipPath": "D:/2026-08-20/FULL/Backup_2026-08-20.zip",
            "transfer": {"type": "local", "verified": True},
        },
        datetime.now(timezone.utc),
    )

    assert item.delivery_status == "local_ready"
    assert item.delivery_phase == "local_ready"
