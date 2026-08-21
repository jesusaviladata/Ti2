from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.core.capabilities import Capability, capabilities_for
from app.models.user import UserRole
from app.schemas.file_backup import (
    FileBackupArtifactPatch,
    FileBackupFilterInput,
    FileBackupScheduleInput,
    FileBackupSourceInput,
    FileBackupTaskCreate,
    FileBackupTaskResponse,
    FileRestoreCreate,
)


def _valid_task_payload() -> dict:
    return {
        "name": "Documentos operativos",
        "agentId": str(uuid.uuid4()),
        "destinationProfileId": str(uuid.uuid4()),
        "sources": [{"path": r"D:\Datos", "includeSubfolders": True}],
        "filters": [
            {"kind": "exclude", "operator": "glob", "pattern": "*.tmp"}
        ],
        "strategy": "incremental",
        "format": "direct",
        "schedule": {"weekdays": [0, 2, 4], "localTime": "02:00"},
        "timezoneName": "America/Mexico_City",
        "retentionFullChains": 4,
        "vssPolicy": "preferred",
        "verificationMode": "sha256",
    }


def test_file_backup_capabilities_are_separate_and_role_scoped():
    required = {
        Capability.FILE_BACKUP_READ,
        Capability.FILE_BACKUP_MANAGE,
        Capability.FILE_BACKUP_RUN,
        Capability.FILE_BACKUP_CANCEL,
        Capability.FILE_BACKUP_PROTECT,
        Capability.FILE_BACKUP_RESTORE,
    }

    assert required <= capabilities_for(UserRole.admin)
    assert Capability.FILE_BACKUP_READ in capabilities_for(UserRole.client)
    assert Capability.FILE_BACKUP_RUN in capabilities_for(UserRole.technician)
    assert Capability.FILE_BACKUP_MANAGE not in capabilities_for(UserRole.technician)
    assert Capability.FILE_BACKUP_PROTECT not in capabilities_for(UserRole.supervisor)


@pytest.mark.parametrize("path", [r"D:\Datos", "C:\\", r"\\fileserver\share\folder"])
def test_source_accepts_absolute_drive_and_unc_paths(path: str):
    source = FileBackupSourceInput(path=path)

    assert source.path == path


@pytest.mark.parametrize(
    "path",
    ["relative/path", r"Datos\Hotel", "/var/data", r"\\server", "", "D:folder"],
)
def test_source_rejects_relative_or_incomplete_paths(path: str):
    with pytest.raises(ValidationError):
        FileBackupSourceInput(path=path)


def test_filter_and_schedule_use_allowlisted_values_and_limits():
    filter_input = FileBackupFilterInput(
        kind="exclude", operator="extension", pattern=".tmp"
    )
    schedule = FileBackupScheduleInput(weekdays=[4, 0, 4], localTime="23:30")

    assert filter_input.operator.value == "extension"
    assert schedule.weekdays == [0, 4]

    with pytest.raises(ValidationError):
        FileBackupFilterInput(kind="exclude", operator="regex", pattern=".*")
    with pytest.raises(ValidationError):
        FileBackupScheduleInput(weekdays=[7], localTime="23:30")
    with pytest.raises(ValidationError):
        FileBackupScheduleInput(weekdays=[1], localTime="25:00")


def test_task_contract_forbids_secrets_and_reports_first_full_behavior():
    task = FileBackupTaskCreate.model_validate(_valid_task_payload())
    dumped = task.model_dump(by_alias=True, mode="json")

    assert task.strategy.value == "incremental"
    assert "secret" not in dumped
    assert "secretEnvelope" not in dumped

    with pytest.raises(ValidationError):
        FileBackupTaskCreate.model_validate(
            {**_valid_task_payload(), "secretEnvelope": "never-store-this"}
        )

    response = FileBackupTaskResponse(
        id=uuid.uuid4(),
        tenantId=uuid.uuid4(),
        configRevision=1,
        isActive=True,
        firstRunWillBeFull=True,
        **_valid_task_payload(),
    )
    assert response.first_run_will_be_full is True


def test_restore_requires_bounded_selection_and_absolute_destination():
    restore = FileRestoreCreate(
        chainId=uuid.uuid4(),
        agentId=uuid.uuid4(),
        destinationMode="alternate",
        destinationPath=r"D:\Restore",
        selections=[r"Core\document.pdf"],
    )

    assert restore.destination_mode == "alternate"

    with pytest.raises(ValidationError):
        FileRestoreCreate(
            chainId=uuid.uuid4(),
            agentId=uuid.uuid4(),
            destinationMode="alternate",
            destinationPath="relative",
            selections=[r"..\escape.txt"],
        )


def test_artifact_patch_only_allows_protection_flag():
    patch = FileBackupArtifactPatch(protected=True)
    assert patch.model_dump() == {"protected": True}

    with pytest.raises(ValidationError):
        FileBackupArtifactPatch.model_validate(
            {"protected": True, "location": r"D:\tampered"}
        )
