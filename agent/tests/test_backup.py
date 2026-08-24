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


def test_direct_backup_requests_native_sql_compression(tmp_path: Path):
    connection = _SuccessfulConnection()
    executor = BackupExecutor()

    executor._backup_database(
        connection,
        "Ipsofactu",
        "full",
        tmp_path / "Ipsofactu.bak",
        compression=True,
    )

    backup_statement = next(
        call for call in connection.calls if call.startswith("BACKUP DATABASE")
    )
    assert "COMPRESSION" in backup_statement
    assert "CHECKSUM" in backup_statement


def test_retry_delivery_uses_existing_verified_zip_without_repeating_sql(tmp_path: Path):
    dated = tmp_path / "2026-08-20"
    dated.mkdir(parents=True)
    zip_path = dated / "Backup_2026-08-20.zip"
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


def test_daily_visible_names_do_not_include_run_id(tmp_path: Path):
    assert backup_member_name("Ipsofactu", "2026-08-20", "full") == (
        "Ipsofactu_2026-08-20.bak"
    )
    assert backup_member_name("Ipsofactu", "2026-08-20", "differential") == (
        "Ipsofactu_2026-08-20_DIF.bak"
    )
    assert daily_archive_path(tmp_path, "2026-08-20", "full") == (
        tmp_path / "2026-08-20" / "Backup_2026-08-20.zip"
    )
    assert daily_archive_path(tmp_path, "2026-08-20", "differential") == (
        tmp_path / "2026-08-20" / "DIFERENCIAL" / "Backup_2026-08-20.zip"
    )


def test_retry_delivery_accepts_legacy_full_folder(tmp_path: Path):
    dated = tmp_path / "2026-08-20" / "FULL"
    dated.mkdir(parents=True)
    zip_path = dated / "Backup_2026-08-20.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("Ipsofactu_2026-08-20.bak", b"validated backup")
        archive.writestr("manifest.json", "{}")
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    executor = BackupExecutor(
        sql_profiles=({"id": "sql-main", "label": "SQL", "backupRoot": str(tmp_path)},),
        destination_profiles=({"id": "remote", "label": "Remoto", "type": "smb"},),
        cleanup_submit=lambda _files, _work_dir: {"scheduled": True},
    )
    seen = {}

    def transfer(path, _destination, date, type_folder):
        seen.update(path=path, date=date, type_folder=type_folder)
        return {"type": "smb", "path": "remote", "verified": True}

    executor._transfer = transfer
    executor.retry_delivery(
        {
            "runId": "run-legacy",
            "sqlProfileId": "sql-main",
            "destinationProfileId": "remote",
            "zipPath": str(zip_path),
            "zipSha256": digest,
        }
    )

    assert seen["date"] == "2026-08-20"
    assert seen["type_folder"] == "FULL"


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


def test_direct_backup_writes_validated_bak_without_zip_or_local_work(tmp_path: Path):
    connection = _SuccessfulConnection()
    destination_root = tmp_path / "remote-share"
    executor = BackupExecutor(
        sql_profiles=({"id": "sql-main", "label": "SQL", "backupRoot": str(tmp_path / "local")},),
        destination_profiles=(
            {"id": "direct", "label": "Directo", "type": "smb_direct", "path": str(destination_root)},
        ),
        connect=lambda _profile: connection,
        now=lambda: __import__("datetime").datetime(2026, 8, 20, 12, 0, 0),
        disk_usage=lambda _root: type("Usage", (), {"free": 10_000, "total": 20_000})(),
        size_history={"Ipsofactu": 100},
    )

    def create_backup(_connection, _database, _backup_type, path, **kwargs):
        path.write_bytes(b"validated direct backup")
        if kwargs.get("phase"):
            kwargs["phase"]("validating_bak")
        return "restore_verifyonly"

    executor._backup_database = create_backup
    result = executor.run_batch(
        {
            "runId": "direct-run",
            "sqlProfileId": "sql-main",
            "databaseNames": ["Ipsofactu"],
            "backupType": "full",
            "destinationProfileId": "direct",
            "deliveryMode": "direct",
            "storageThresholds": {"criticalFreeBytes": 10},
        },
        allow_local_direct_path=True,
    )

    final_path = destination_root / "2026-08-20" / "Ipsofactu_2026-08-20.bak"
    assert final_path.read_bytes() == b"validated direct backup"
    assert result["deliveryMode"] == "direct"
    assert result["transfer"]["type"] == "smb_direct"
    assert result["databases"][0]["filePath"] == str(final_path)
    assert "zipPath" not in result
    assert not (tmp_path / "local" / ".work").exists()


def test_direct_backup_rejects_existing_final_artifact(tmp_path: Path):
    destination_root = tmp_path / "remote-share"
    dated = destination_root / "2026-08-20"
    dated.mkdir(parents=True)
    (dated / "Ipsofactu_2026-08-20.bak").write_bytes(b"previous")
    executor = BackupExecutor(
        sql_profiles=({"id": "sql-main", "backupRoot": str(tmp_path / "local")},),
        destination_profiles=(
            {"id": "direct", "type": "smb_direct", "path": str(destination_root)},
        ),
        connect=lambda _profile: _SuccessfulConnection(),
        now=lambda: __import__("datetime").datetime(2026, 8, 20, 12, 0, 0),
        disk_usage=lambda _root: type("Usage", (), {"free": 10_000, "total": 20_000})(),
        size_history={"Ipsofactu": 100},
    )

    with pytest.raises(BackupError) as rejected:
        executor.run_batch(
            {
                "runId": "direct-conflict",
                "sqlProfileId": "sql-main",
                "databaseNames": ["Ipsofactu"],
                "backupType": "full",
                "destinationProfileId": "direct",
                "deliveryMode": "direct",
                "storageThresholds": {"criticalFreeBytes": 10},
            },
            allow_local_direct_path=True,
        )

    assert rejected.value.code == "DIRECT_BACKUP_CONFLICT"
