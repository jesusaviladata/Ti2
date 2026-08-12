from __future__ import annotations

from datetime import datetime
from pathlib import Path

from agent.data_express_agent.backup import BackupError, BackupExecutor, _sql_unicode_literal


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


def test_backup_batch_creates_dated_folder_verified_baks_and_zip(tmp_path):
    connection = FakeConnection()
    executor = BackupExecutor(
        sql_profiles=(
            {"id": "local", "label": "SQL local", "server": ".", "backupRoot": str(tmp_path)},
        ),
        connect=lambda _profile: connection,
        now=lambda: datetime(2026, 8, 12, 10, 30, 0),
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
    assert all(item["verified"] for item in result["databases"])
    assert all(item["verificationMethod"] == "restore_verifyonly" for item in result["databases"])
    assert all("COMPRESSION" not in sql for sql in connection.statements)
    assert progress[-1]["phase"] == "completed"


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
