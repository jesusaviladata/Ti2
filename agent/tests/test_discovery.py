from __future__ import annotations

from agent.data_express_agent.discovery import discover_environment


def test_discovery_reports_public_candidates_and_volumes_without_listing_files(monkeypatch):
    class Usage:
        total = 1_000
        free = 400

    monkeypatch.setattr(
        "agent.data_express_agent.discovery.shutil.disk_usage", lambda _root: Usage()
    )
    result = discover_environment(
        (
            {
                "id": "sql-main",
                "profileKey": "sql-main",
                "label": "SQL principal",
                "server": "localhost",
                "backupRoot": "D:\\Backups",
                "requiresSecret": False,
            },
        ),
        (
            {
                "id": "central",
                "profileKey": "central",
                "label": "Central",
                "type": "sftp",
                "path": "/backups",
                "host": "backup.internal",
                "privateKeyPath": "C:\\keys\\central_ed25519",
            },
        ),
    )

    assert result["sqlCandidates"][0]["profileKey"] == "sql-main"
    assert result["destinationCandidates"][0]["hasLocalPrivateKey"] is True
    assert result["volumeCandidates"] == [
        {"mountPoint": "D:\\", "totalBytes": 1_000, "freeBytes": 400}
    ]
    assert "files" not in result
