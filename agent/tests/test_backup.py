from __future__ import annotations

from datetime import datetime
from pathlib import Path

from agent.data_express_agent.backup import BackupExecutor


class FakeRows:
    def fetchall(self):
        return [("DX",), ("IPSOFACTU",)]


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, *parameters):
        if sql.startswith("SELECT name"):
            return FakeRows()
        if sql.startswith("BACKUP"):
            path = Path(parameters[0])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((path.stem * 100).encode("utf-8"))
        return self


def test_lists_databases_from_configured_profile(tmp_path):
    executor = BackupExecutor(
        sql_profiles=(
            {"id": "local", "label": "SQL local", "server": ".", "backupRoot": str(tmp_path)},
        ),
        connect=lambda _profile: FakeConnection(),
    )

    result = executor.list_databases("local")

    assert result["databases"] == ["DX", "IPSOFACTU"]


def test_backup_batch_creates_dated_folder_verified_baks_and_zip(tmp_path):
    executor = BackupExecutor(
        sql_profiles=(
            {"id": "local", "label": "SQL local", "server": ".", "backupRoot": str(tmp_path)},
        ),
        connect=lambda _profile: FakeConnection(),
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
    assert progress[-1]["phase"] == "completed"
