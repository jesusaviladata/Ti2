from pathlib import Path
import hashlib
import zipfile

import pytest

from agent.data_express_agent.backup import BackupError, BackupExecutor


class _Cursor:
    def nextset(self):
        return False


class _PermissionDeniedConnection:
    def __init__(self):
        self.calls = []

    def execute(self, sql):
        self.calls.append(sql)
        if sql.startswith("RESTORE VERIFYONLY"):
            raise RuntimeError(
                "CREATE DATABASE permission denied in database 'master'"
            )
        return _Cursor()


class _SuccessfulConnection:
    def __init__(self):
        self.calls = []

    def execute(self, sql):
        self.calls.append(sql)
        return _Cursor()


def test_backup_validation_permission_failure_is_not_accepted(tmp_path: Path):
    executor = BackupExecutor()

    with pytest.raises(BackupError) as rejected:
        executor._backup_database(
            _PermissionDeniedConnection(),
            "Ipsofactu",
            "full",
            tmp_path / "Ipsofactu_FULL.bak",
        )

    assert rejected.value.code == "BACKUP_VALIDATION_FAILED"


def test_backup_is_ready_only_after_restore_verifyonly(tmp_path: Path):
    connection = _SuccessfulConnection()
    executor = BackupExecutor()
    phases = []

    method = executor._backup_database(
        connection,
        "Ipsofactu",
        "full",
        tmp_path / "Ipsofactu_FULL.bak",
        phase=phases.append,
    )

    assert method == "restore_verifyonly"
    assert phases == ["validating_bak"]
    assert any(call.startswith("RESTORE VERIFYONLY") for call in connection.calls)


def test_retry_delivery_uses_existing_verified_zip_without_repeating_sql(tmp_path: Path):
    dated = tmp_path / "2026-08-20"
    dated.mkdir()
    zip_path = dated / "Backup_run-1.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("Ipsofactu_FULL.bak", b"validated backup")
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    executor = BackupExecutor(
        sql_profiles=({"id": "sql-main", "label": "SQL", "backupRoot": str(tmp_path)},),
        destination_profiles=({"id": "remote", "label": "Remoto", "type": "smb"},),
        connect=lambda _profile: (_ for _ in ()).throw(AssertionError("SQL must not run")),
        cleanup_submit=lambda _files, _work_dir: {"scheduled": True},
    )
    executor._transfer = lambda path, _destination, date: {
        "type": "smb", "path": f"remote/{date}/{path.name}", "verified": True
    }

    result = executor.retry_delivery(
        {
            "runId": "run-1",
            "sqlProfileId": "sql-main",
            "destinationProfileId": "remote",
            "zipPath": str(zip_path),
            "zipSha256": digest,
        }
    )

    assert result["zipSha256"] == digest
    assert result["transfer"]["verified"] is True
