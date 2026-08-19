from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time

from agent.data_express_agent.backup import (
    BackupError,
    BackupExecutor,
    _consume_sql_results,
    _normalize_host_key_sha256,
    _remove_work_files,
    _sql_unicode_literal,
    _wait_for_backup_file,
)


class FakeRows:
    def fetchall(self):
        return [("DX",), ("IPSOFACTU",)]


class FakeConnection:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, *parameters):
        self.statements.append(sql)
        if sql.startswith("SELECT name"):
            return FakeRows()
        if sql.startswith("BACKUP"):
            assert parameters == ()
            path_text = sql.split("TO DISK = N'", 1)[1].split("' WITH", 1)[0]
            path = Path(path_text.replace("''", "'"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((path.stem * 100).encode("utf-8"))
        return self


class ExpressVerifyPermissionConnection(FakeConnection):
    def execute(self, sql, *parameters):
        if sql.startswith("RESTORE VERIFYONLY"):
            raise RuntimeError(
                "CREATE DATABASE permission denied in database 'master'."
            )
        return super().execute(sql, *parameters)


def test_lists_databases_from_configured_profile(tmp_path):
    executor = BackupExecutor(
        sql_profiles=(
            {"id": "local", "label": "SQL local", "server": ".", "backupRoot": str(tmp_path)},
        ),
        connect=lambda _profile: FakeConnection(),
    )

    result = executor.list_databases("local")

    assert result["databases"] == ["DX", "IPSOFACTU"]


def test_sql_unicode_literal_escapes_apostrophes():
    assert _sql_unicode_literal("D:\\O'Brien\\file.bak") == "N'D:\\O''Brien\\file.bak'"


def test_host_key_fingerprint_accepts_openssh_and_padded_base64_forms():
    value = "9ivhCg8rhBjNrd7vDBdYgirazO29JmC7FyozQP7+ZRY"

    assert _normalize_host_key_sha256(f"SHA256:{value}") == value
    assert _normalize_host_key_sha256(f"{value}=") == value


def test_wait_for_backup_file_retries_until_sql_server_materializes_it(tmp_path, monkeypatch):
    path = tmp_path / "backup.bak"
    calls = []

    def sleep(_seconds):
        calls.append(1)
        if len(calls) == 2:
            path.write_bytes(b"backup")

    assert _wait_for_backup_file(path, timeout_seconds=5, sleep=sleep) is True
    assert len(calls) == 2


def test_consume_sql_results_drains_all_sets():
    class Cursor:
        def __init__(self):
            self.calls = 0

        def nextset(self):
            self.calls += 1
            return self.calls < 3

    cursor = Cursor()
    _consume_sql_results(cursor)
    assert cursor.calls == 3


def test_backup_error_includes_redacted_database_diagnostic(tmp_path):
    class BrokenConnection(FakeConnection):
        def execute(self, sql, *parameters):
            if sql.startswith("BACKUP"):
                raise RuntimeError("[HY000] backup denied; PWD=topsecret")
            return super().execute(sql, *parameters)

    executor = BackupExecutor(
        sql_profiles=({"id": "local", "server": ".", "backupRoot": str(tmp_path)},),
        connect=lambda _profile: BrokenConnection(),
    )

    try:
        executor.run_batch({"sqlProfileId": "local", "databaseNames": ["DX"]})
    except BackupError as exc:
        assert "backup denied" in str(exc)
        assert "topsecret" not in str(exc)
    else:
        raise AssertionError("Expected BackupError")


def test_backup_batch_creates_verified_zip_and_removes_temporary_baks(tmp_path):
    connection = FakeConnection()
    executor = BackupExecutor(
        sql_profiles=(
            {"id": "local", "label": "SQL local", "server": ".", "backupRoot": str(tmp_path)},
        ),
        connect=lambda _profile: connection,
        now=lambda: datetime(2026, 8, 12, 10, 30, 0),
        cleanup_submit=_remove_work_files,
    )
    progress = []

    result = executor.run_batch(
        {
            "runId": "job-123",
            "sqlProfileId": "local",
            "databaseNames": ["DX", "IPSOFACTU"],
            "backupType": "full",
        },
        progress=progress.append,
    )

    assert Path(result["folder"]).name == "2026-08-12"
    assert Path(result["zipPath"]).is_file()
    assert result["zipSizeBytes"] > 0
    assert len(result["zipSha256"]) == 64
    assert [item["databaseName"] for item in result["databases"]] == ["DX", "IPSOFACTU"]
    assert [item["fileName"] for item in result["databases"]] == [
        "DX_FULL.bak",
        "IPSOFACTU_FULL.bak",
    ]
    assert all(item["verified"] for item in result["databases"])
    assert all(item["verificationMethod"] == "restore_verifyonly" for item in result["databases"])
    assert all("COMPRESSION" not in sql for sql in connection.statements)
    assert result["localSourceCleanup"]["complete"] is True
    assert len(result["localSourceCleanup"]["deletedFiles"]) == 2
    assert list(tmp_path.rglob("*.bak")) == []
    assert not (tmp_path / "2026-08-12" / ".work").exists()
    assert "cleaning_up" not in [item["phase"] for item in progress]
    assert progress[-1]["phase"] == "completed"


def test_temporary_backup_cleanup_runs_in_background(tmp_path):
    work_dir = tmp_path / "2026-08-12" / ".work" / "job-background"
    work_dir.mkdir(parents=True)
    backup = work_dir / "DX_FULL.bak"
    backup.write_bytes(b"backup")
    executor = BackupExecutor()

    result = executor._schedule_cleanup([backup], work_dir)

    assert result["scheduled"] is True
    deadline = time.monotonic() + 2
    while backup.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not backup.exists()


def test_backup_batch_uses_file_hash_when_express_cannot_run_restore_verifyonly(tmp_path):
    executor = BackupExecutor(
        sql_profiles=(
            {"id": "local", "label": "SQL local", "server": ".", "backupRoot": str(tmp_path)},
        ),
        connect=lambda _profile: ExpressVerifyPermissionConnection(),
        now=lambda: datetime(2026, 8, 12, 10, 30, 0),
    )

    result = executor.run_batch(
        {
            "runId": "job-express",
            "sqlProfileId": "local",
            "databaseNames": ["DX"],
            "backupType": "full",
        }
    )

    database = result["databases"][0]
    assert database["verified"] is True
    assert database["verificationMethod"] == "file_sha256"
    assert len(database["fileSha256"]) == 64


def test_backup_batch_retains_temporary_baks_when_transfer_fails(tmp_path, monkeypatch):
    executor = BackupExecutor(
        sql_profiles=({"id": "local", "server": ".", "backupRoot": str(tmp_path)},),
        destination_profiles=(
            {"id": "remote", "label": "Remote", "type": "sftp"},
        ),
        connect=lambda _profile: FakeConnection(),
        now=lambda: datetime(2026, 8, 12, 10, 30, 0),
    )

    def fail_transfer(*_args):
        raise BackupError("SFTP_TRANSFER_FAILED", "transfer failed")

    monkeypatch.setattr(executor, "_transfer", fail_transfer)

    try:
        executor.run_batch(
            {
                "runId": "job-transfer-failure",
                "sqlProfileId": "local",
                "databaseNames": ["DX"],
                "backupType": "full",
                "destinationProfileId": "remote",
            }
        )
    except BackupError as exc:
        assert exc.code == "SFTP_TRANSFER_FAILED"
    else:
        raise AssertionError("Expected BackupError")

    retained = list(
        (tmp_path / "2026-08-12" / ".work" / "job-transfer-failure").glob("*.bak")
    )
    assert len(retained) == 1
