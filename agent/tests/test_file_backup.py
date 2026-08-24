from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from agent.data_express_agent.file_backup import FileBackupError, FileBackupExecutor


def _executor(tmp_path: Path) -> FileBackupExecutor:
    return FileBackupExecutor(
        tmp_path / "state",
        destination_profiles=(
            {
                "id": "destination-main",
                "label": "Destino",
                "type": "local",
                "path": str(tmp_path / "destination"),
            },
        ),
        now=lambda: datetime(2026, 8, 24, 2, 0, 0),
        allow_test_paths=True,
    )


def _payload(tmp_path: Path, *, run_id: str = "run-full", strategy: str = "full") -> dict:
    return {
        "fileRunId": run_id,
        "taskId": "task-documents",
        "taskName": "Documentos oficina",
        "configRevision": 1,
        "strategy": strategy,
        "format": "direct",
        "sources": [
            {"path": str(tmp_path / "source"), "includeSubfolders": True}
        ],
        "filters": [
            {"kind": "exclude", "operator": "extension", "pattern": ".tmp", "isEnabled": True}
        ],
        "destinationProfileId": "destination-main",
        "retentionFullChains": 2,
        "verificationMode": "sha256",
    }


def test_simulation_applies_filters_and_does_not_copy(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "keep.txt").write_text("important", encoding="utf-8")
    (source / "ignore.tmp").write_text("temporary", encoding="utf-8")
    executor = _executor(tmp_path)

    result = executor.execute("simulate_file_backup", _payload(tmp_path), lambda _item: None)

    assert result["status"] == "completed"
    assert result["summary"]["filesTotal"] == 1
    assert result["summary"]["bytesTotal"] == len(b"important")
    assert result["summary"]["excludedCount"] == 1
    assert not (tmp_path / "destination").exists()


def test_full_backup_copies_verifies_manifests_and_catalogs_files(tmp_path: Path):
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "one.txt").write_text("one", encoding="utf-8")
    (source / "two.bin").write_bytes(b"two")
    progress = []
    executor = _executor(tmp_path)

    result = executor.execute("run_file_backup", _payload(tmp_path), progress.append)

    artifact = Path(result["artifact"]["location"])
    assert result["status"] == "completed"
    assert result["effectiveStrategy"] == "full"
    assert result["summary"]["filesCopied"] == 2
    assert (artifact / "Fuente-1" / "nested" / "one.txt").read_text() == "one"
    manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == 1
    assert len(manifest["files"]) == 2
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])
    assert executor.catalog_revision == 1
    assert progress[-1]["phase"] == "completed"


def test_incremental_copies_only_changes_after_a_confirmed_full(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    unchanged = source / "unchanged.txt"
    changed = source / "changed.txt"
    unchanged.write_text("same", encoding="utf-8")
    changed.write_text("before", encoding="utf-8")
    executor = _executor(tmp_path)
    executor.execute("run_file_backup", _payload(tmp_path), lambda _item: None)
    changed.write_text("after and larger", encoding="utf-8")

    result = executor.execute(
        "run_file_backup",
        _payload(tmp_path, run_id="run-incremental", strategy="incremental"),
        lambda _item: None,
    )

    artifact = Path(result["artifact"]["location"])
    assert result["effectiveStrategy"] == "incremental"
    assert result["summary"]["filesCopied"] == 1
    assert (artifact / "Fuente-1" / "changed.txt").exists()
    assert not (artifact / "Fuente-1" / "unchanged.txt").exists()


def test_first_incremental_is_promoted_to_full(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("content", encoding="utf-8")
    executor = _executor(tmp_path)

    result = executor.execute(
        "run_file_backup",
        _payload(tmp_path, strategy="incremental"),
        lambda _item: None,
    )

    assert result["effectiveStrategy"] == "full"


def test_existing_visible_artifact_is_never_overwritten(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("content", encoding="utf-8")
    executor = _executor(tmp_path)
    executor.execute("run_file_backup", _payload(tmp_path), lambda _item: None)

    with pytest.raises(FileBackupError) as rejected:
        executor.execute(
            "run_file_backup",
            _payload(tmp_path, run_id="another-run"),
            lambda _item: None,
        )

    assert rejected.value.code == "FILE_BACKUP_ARTIFACT_CONFLICT"


def test_source_root_and_reparse_points_are_rejected(tmp_path: Path):
    executor = _executor(tmp_path)
    payload = _payload(tmp_path)
    payload["sources"] = [{"path": str(Path(tmp_path.anchor)), "includeSubfolders": True}]

    with pytest.raises(FileBackupError) as rejected:
        executor.execute("simulate_file_backup", payload, lambda _item: None)

    assert rejected.value.code == "FILE_BACKUP_SOURCE_ROOT_FORBIDDEN"
