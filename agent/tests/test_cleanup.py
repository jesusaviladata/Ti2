from pathlib import Path

import pytest

from agent.data_express_agent.cleanup import CleanupError, StructuralCleanupExecutor


FIXED_FOLDERS = ["Log", "LogSec", "LogsRadian", "Respuesta"]
FIXED_FILES = ["BD_log.txt"]


def _payload(root: Path, **overrides):
    payload = {
        "root": str(root),
        "containerFolder": "core",
        "targetFolders": FIXED_FOLDERS,
        "targetFiles": FIXED_FILES,
    }
    payload.update(overrides)
    return payload


def test_simulation_empties_every_file_type_but_preserves_scope(tmp_path: Path):
    root = tmp_path / "properties"
    log = root / "Hotel-A" / "core" / "Log"
    nested = log / "archive"
    nested.mkdir(parents=True)
    (log / "runtime.exe").write_bytes(b"binary log")
    (nested / "snapshot.bak").write_bytes(b"backup-shaped log")
    (root / "Hotel-A" / "core" / "database.mdf").write_bytes(b"protected")
    executor = StructuralCleanupExecutor(tmp_path / "agent-data")

    report = executor.simulate(_payload(root))

    assert report["eligibleCount"] == 2
    assert report["protectedCount"] == 0
    paths = {Path(item["relativePath"]).name for item in report["samples"]}
    assert paths == {"runtime.exe", "snapshot.bak"}


def test_simulation_rejects_targets_outside_fixed_policy(tmp_path: Path):
    root = tmp_path / "properties"
    root.mkdir()
    executor = StructuralCleanupExecutor(tmp_path / "agent-data")

    with pytest.raises(CleanupError) as rejected:
        executor.simulate(_payload(root, targetFolders=["OtherLogs"]))

    assert rejected.value.code == "CLEANUP_POLICY_INVALID"


def test_direct_cleanup_deletes_files_and_keeps_directories(tmp_path: Path):
    root = tmp_path / "properties"
    nested = root / "Hotel-A" / "core" / "Respuesta" / "2026"
    nested.mkdir(parents=True)
    target = nested / "response.json"
    target.write_text("{}", encoding="utf-8")
    executor = StructuralCleanupExecutor(tmp_path / "agent-data")
    report = executor.simulate(_payload(root))

    result = executor.execute_direct(
        {
            "simulationId": report["simulationId"],
            "manifestHash": report["manifestHash"],
        }
    )

    assert result["deletedCount"] == 1
    assert not target.exists()
    assert nested.is_dir()
