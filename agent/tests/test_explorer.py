from __future__ import annotations

from pathlib import Path

import pytest

from agent.data_express_agent.explorer import ExplorerError, WindowsExplorer


def _make_property(root: Path, name: str, *, core: str | None = "Core", web=True):
    property_path = root / name
    property_path.mkdir()
    if core:
        (property_path / core).mkdir()
    if web:
        (property_path / "Web").mkdir()
    return property_path


def test_validation_treats_direct_children_as_properties_and_only_reads_core(tmp_path):
    first = _make_property(tmp_path, "Hotel Norte")
    (first / "Core" / "Logs").mkdir()
    (first / "Core" / "BD_log.txt").write_text("metadata", encoding="utf-8")
    (first / "Web" / "Logs").mkdir()
    _make_property(tmp_path, "Hotel Sur", core="cOrE", web=False)
    _make_property(tmp_path, "Hotel Sin Core", core=None)

    result = WindowsExplorer().validate_structure(
        str(tmp_path), target_folders=["Logs"], target_files=["BD_log.txt"]
    )

    assert result["valid"] is True
    assert result["propertiesDetected"] == 3
    assert result["propertiesWithCore"] == 2
    assert result["propertiesWithoutCore"] == 1
    assert result["propertiesWithWeb"] == 2
    assert result["targetFolders"] == {"Logs": 1}
    assert result["targetFiles"] == {"BD_log.txt": 1}


def test_browsing_returns_directories_only_without_opening_files(tmp_path):
    (tmp_path / "Folder B").mkdir()
    (tmp_path / "Folder A").mkdir()
    (tmp_path / "secret.txt").write_text("do not return", encoding="utf-8")

    result = WindowsExplorer().browse_directory(str(tmp_path))

    assert [item["name"] for item in result["directories"]] == ["Folder A", "Folder B"]
    assert "secret.txt" not in str(result)


@pytest.mark.parametrize("target", ["Web", "Core", "../Logs", "folder:stream", ""])
def test_dangerous_or_structural_target_names_are_rejected(tmp_path, target):
    _make_property(tmp_path, "Hotel")
    with pytest.raises(ExplorerError) as rejected:
        WindowsExplorer().validate_structure(
            str(tmp_path), target_folders=[target], target_files=[]
        )
    assert rejected.value.code == "TARGET_NAME_INVALID"


def test_validation_progress_is_bounded_and_observable(tmp_path):
    for index in range(25):
        _make_property(tmp_path, f"Property {index:03}", web=False)
    progress = []

    result = WindowsExplorer().validate_structure(
        str(tmp_path),
        target_folders=["Log", "LogSec", "LogsRadian", "Respuesta"],
        target_files=["BD_log.txt"],
        progress=lambda processed, total: progress.append((processed, total)),
    )

    assert progress[-1] == (25, 25)
    assert result["propertiesProcessed"] == 25

