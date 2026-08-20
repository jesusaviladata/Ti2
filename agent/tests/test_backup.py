from pathlib import Path
import hashlib
import zipfile

import pytest

from agent.data_express_agent.backup import (
    BackupError,
    BackupExecutor,
    backup_member_name,
    daily_archive_path,
)


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

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql):
        self.calls.append(sql)
        if sql.startswith("SELECT DB_NAME"):
            return type("Rows", (), {"fetchall": lambda self: [("Ipsofactu", 100)]})()
        return _Cursor()


def test_preflight_rejects_backup_before_sql_when_critical_reserve_would_be_invaded(tmp_path: Path):
    connection = _SuccessfulConnection()
    executor = BackupExecutor(
        sql_profiles=(
            {"id": "sql-main", "label": "SQL", "backupRoot": str(tmp_path)},
        ),
        connect=lambda _profile: connection,
        disk_usage=lambda _root: type("Usage", (), {"free": 150})(),
    )

    with pytest.raises(BackupError) as rejected:
        executor.run_batch(
            {
                "sqlProfileId": "sql-main",
                "databaseNames": ["Ipsofactu"],
                "backupType": "full",
                "storageThresholds": {"criticalFreeBytes": 10},
            }
        )

    assert rejected.value.code == "BACKUP_SPACE_INSUFFICIENT"
    assert not any(call.startswith("BACKUP DATABASE") for call in connection.calls)


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
    dated = tmp_path / "2026-08-20" / "FULL"
    dated.mkdir(parents=True)
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
    executor._transfer = lambda path, _destination, date, type_folder: {
        "type": "smb", "path": f"remote/{date}/{type_folder}/{path.name}", "verified": True
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


def test_daily_visible_names_do_not_include_run_id(tmp_path: Path):
    assert backup_member_name("Ipsofactu", "2026-08-20", "full") == (
        "Ipsofactu_2026-08-20.bak"
    )
    assert backup_member_name("Ipsofactu", "2026-08-20", "differential") == (
        "Ipsofactu_2026-08-20_DIF.bak"
    )
    assert daily_archive_path(tmp_path, "2026-08-20", "full") == (
        tmp_path / "2026-08-20" / "FULL" / "Backup_2026-08-20.zip"
    )
    assert daily_archive_path(tmp_path, "2026-08-20", "differential") == (
        tmp_path / "2026-08-20" / "DIFERENCIAL" / "Backup_2026-08-20.zip"
    )


def test_atomic_archive_keeps_previous_daily_zip_if_replacement_fails(tmp_path: Path):
    final_path = tmp_path / "Backup_2026-08-20.zip"
    with zipfile.ZipFile(final_path, "w") as archive:
        archive.writestr("previous.bak", b"previous valid backup")
        archive.writestr("manifest.json", "{}")
    previous_hash = hashlib.sha256(final_path.read_bytes()).hexdigest()

    with pytest.raises(FileNotFoundError):
        BackupExecutor._build_archive_atomically(
            [tmp_path / "missing.bak"],
            final_path,
            {"version": 1},
            "new-run",
        )

    assert hashlib.sha256(final_path.read_bytes()).hexdigest() == previous_hash
    assert not list(tmp_path.glob("*.tmp"))
