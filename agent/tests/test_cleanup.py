from __future__ import annotations

from agent.data_express_agent.cleanup import StructuralCleanupExecutor


def test_cleanup_simulation_quarantine_restore_and_purge(tmp_path):
    root = tmp_path / "Ipsofactu"
    logs = root / "P001" / "Core" / "Log"
    logs.mkdir(parents=True)
    removable = logs / "old.log"
    protected = logs / "important.bak"
    removable.write_text("old log", encoding="utf-8")
    protected.write_text("backup", encoding="utf-8")
    executor = StructuralCleanupExecutor(tmp_path / "agent-data")

    simulation = executor.simulate(
        {
            "root": str(root),
            "containerFolder": "Core",
            "targetFolders": ["Log"],
            "targetFiles": [],
        }
    )

    assert simulation["eligibleCount"] == 1
    assert simulation["protectedCount"] == 1
    execution = executor.execute_quarantine(
        {
            "simulationId": simulation["simulationId"],
            "manifestHash": simulation["manifestHash"],
            "executionId": "execution-1",
        }
    )
    assert execution["movedCount"] == 1
    assert not removable.exists()
    assert protected.exists()

    restored = executor.restore(
        {"root": str(root), "executionId": "execution-1"}
    )
    assert restored["restoredCount"] == 1
    assert removable.exists()

    second = executor.simulate(
        {
            "root": str(root),
            "containerFolder": "Core",
            "targetFolders": ["Log"],
            "targetFiles": [],
        }
    )
    executor.execute_quarantine(
        {
            "simulationId": second["simulationId"],
            "manifestHash": second["manifestHash"],
            "executionId": "execution-2",
        }
    )
    purged = executor.purge({"root": str(root), "executionId": "execution-2"})
    assert purged["purged"] is True
    assert not removable.exists()


def test_cleanup_detects_changed_file_after_simulation(tmp_path):
    root = tmp_path / "Ipsofactu"
    logs = root / "P001" / "Core" / "Log"
    logs.mkdir(parents=True)
    candidate = logs / "old.log"
    candidate.write_text("before", encoding="utf-8")
    executor = StructuralCleanupExecutor(tmp_path / "agent-data")
    simulation = executor.simulate(
        {
            "root": str(root),
            "containerFolder": "Core",
            "targetFolders": ["Log"],
            "targetFiles": [],
        }
    )
    candidate.write_text("changed after simulation", encoding="utf-8")

    result = executor.execute_quarantine(
        {
            "simulationId": simulation["simulationId"],
            "manifestHash": simulation["manifestHash"],
            "executionId": "execution-changed",
        }
    )

    assert result["movedCount"] == 0
    assert result["failedCount"] == 1
    assert candidate.exists()


def test_cleanup_direct_deletes_only_unchanged_unprotected_files(tmp_path):
    root = tmp_path / "Ipsofactu"
    logs = root / "P001" / "Core" / "Log"
    logs.mkdir(parents=True)
    removable = logs / "trace.log"
    protected = logs / "respaldo.zip"
    removable.write_text("log", encoding="utf-8")
    protected.write_text("zip", encoding="utf-8")
    executor = StructuralCleanupExecutor(tmp_path / "agent-data")

    simulation = executor.simulate(
        {
            "root": str(root),
            "containerFolder": "Core",
            "targetFolders": ["Log"],
            "targetFiles": [],
        }
    )
    result = executor.execute_direct(
        {
            "simulationId": simulation["simulationId"],
            "manifestHash": simulation["manifestHash"],
        }
    )

    assert result["deletedCount"] == 1
    assert result["failedCount"] == 0
    assert not removable.exists()
    assert protected.exists()


def test_cleanup_simulation_applies_file_and_byte_limits(tmp_path):
    root = tmp_path / "Ipsofactu"
    logs = root / "P001" / "Core" / "Log"
    logs.mkdir(parents=True)
    for name in ("a.log", "b.log", "c.log"):
        (logs / name).write_text("1234", encoding="utf-8")
    executor = StructuralCleanupExecutor(tmp_path / "agent-data")

    simulation = executor.simulate(
        {
            "root": str(root),
            "containerFolder": "Core",
            "targetFolders": ["Log"],
            "targetFiles": [],
            "maxFiles": 2,
            "maxBytes": 4,
        }
    )

    assert simulation["eligibleCount"] == 1
    assert simulation["bytesEligible"] == 4
    assert simulation["truncated"] is True
