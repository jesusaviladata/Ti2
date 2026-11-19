"""Descubrimiento recursivo de propiedades Ipsofactu (raíz = unidad o carpeta de grupo)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.data_express_agent import property_discovery as discovery_module
from agent.data_express_agent.cleanup import CleanupError, StructuralCleanupExecutor
from agent.data_express_agent.property_discovery import discover_properties
from agent.data_express_agent.explorer import ExplorerError, WindowsExplorer

FOLDERS = ["Log", "LogSec", "LogsRadian", "Respuesta"]
FILES = ["BD_log.txt"]


def _ipsofactu(property_path: Path, *, logs: int = 1) -> Path:
    core = property_path / "core"
    for name in ("Log", "LogSec"):
        (core / name).mkdir(parents=True, exist_ok=True)
    for index in range(logs):
        (core / "Log" / f"{index}.log").write_text("x" * 10, encoding="utf-8")
    (core / "BD_log.txt").write_text("bd", encoding="utf-8")
    return property_path


def _layout(root: Path) -> None:
    # Rutas reales del cliente, a distinta profundidad.
    _ipsofactu(root / "Aplicaciones" / "DataExpress publications" / "DX" / "Test" / "Clientes" / "Hoteles Elite")
    _ipsofactu(root / "IpsofactuPE" / "IPSOFACTU" / "EMPRESAS" / "PE" / "PE", logs=3)
    _ipsofactu(root / "Publicaciones" / "DX")
    # Aplicación ajena con su propio core\Log: NO es una propiedad.
    (root / "Aplicaciones" / "OtraApp" / "core" / "Log").mkdir(parents=True)
    (root / "Aplicaciones" / "OtraApp" / "core" / "Log" / "app.log").write_text("ajeno", encoding="utf-8")
    # Carpeta de sistema que se debe omitir aunque parezca una propiedad.
    _ipsofactu(root / "System Volume Information" / "Falsa")


def test_discovers_properties_at_any_depth_and_ignores_foreign_core(tmp_path):
    _layout(tmp_path)

    result = discover_properties(tmp_path, target_folders=FOLDERS, target_files=FILES)

    found = [item.relative.replace("\\", "/") for item in result.properties]
    assert found == [
        "Aplicaciones/DataExpress publications/DX/Test/Clientes/Hoteles Elite",
        "IpsofactuPE/IPSOFACTU/EMPRESAS/PE/PE",
        "Publicaciones/DX",
    ]
    assert not result.truncated


def test_depth_limit_stops_descent(tmp_path):
    _layout(tmp_path)

    result = discover_properties(tmp_path, target_folders=FOLDERS, target_files=FILES, max_depth=3)

    assert [item.relative.replace("\\", "/") for item in result.properties] == ["Publicaciones/DX"]


def test_first_level_of_a_property_folder_keeps_historic_behaviour(tmp_path):
    (tmp_path / "Hotel Sur" / "cOrE").mkdir(parents=True)  # core vacío
    _ipsofactu(tmp_path / "Hotel Norte")

    result = discover_properties(tmp_path, target_folders=FOLDERS, target_files=FILES)

    assert [item.relative for item in result.properties] == ["Hotel Norte", "Hotel Sur"]


def test_does_not_descend_into_a_property(tmp_path):
    outer = _ipsofactu(tmp_path / "Grupo" / "Hotel")
    _ipsofactu(outer / "Anidada")

    result = discover_properties(tmp_path, target_folders=FOLDERS, target_files=FILES)

    assert [item.relative.replace("\\", "/") for item in result.properties] == ["Grupo/Hotel"]


def test_folder_budget_marks_result_truncated(tmp_path):
    _layout(tmp_path)

    result = discover_properties(tmp_path, target_folders=FOLDERS, target_files=FILES, max_folders=3)

    assert result.truncated is True


def test_validation_lists_nested_properties(tmp_path):
    _layout(tmp_path)

    result = WindowsExplorer().validate_structure(str(tmp_path), target_folders=FOLDERS, target_files=FILES)

    assert result["valid"] is True
    assert result["propertiesDetected"] == 3
    assert result["maxDepth"] == 6
    assert result["targetFolders"]["Log"] == 3
    assert result["targetFiles"]["BD_log.txt"] == 3
    assert {item["path"].replace("\\", "/") for item in result["properties"]} >= {"Publicaciones/DX"}


def test_validation_is_invalid_when_no_property_has_the_signature(tmp_path):
    (tmp_path / "Aplicaciones" / "OtraApp" / "core" / "Log").mkdir(parents=True)

    result = WindowsExplorer().validate_structure(str(tmp_path), target_folders=FOLDERS, target_files=FILES)

    assert result["valid"] is False
    assert result["propertiesDetected"] == 0


def test_system_drive_root_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery_module, "is_system_drive_root", lambda root: True)

    with pytest.raises(ExplorerError) as rejected:
        WindowsExplorer().validate_structure(str(tmp_path), target_folders=FOLDERS, target_files=FILES)
    assert rejected.value.code == "ROOT_TOO_BROAD"


def test_simulation_cleans_nested_properties_only_and_reports_breakdown(tmp_path):
    root = tmp_path / "D"
    _layout(root)
    executor = StructuralCleanupExecutor(tmp_path / "agent-data")

    simulation = executor.simulate(
        {"root": str(root), "containerFolder": "Core", "targetFolders": FOLDERS, "targetFiles": FILES}
    )

    paths = {Path(item["relativePath"]).as_posix().casefold() for item in simulation["samples"]}
    assert "aplicaciones/otraapp/core/log/app.log" not in paths
    assert "publicaciones/dx/core/log/0.log" in paths
    assert simulation["propertiesAffected"] == 3
    assert simulation["eligibleCount"] == 1 + 1 + 3 + 1 + 1 + 1  # logs + BD_log.txt por propiedad
    summary = {Path(item["path"]).as_posix(): item for item in simulation["propertySummary"]}
    assert summary["IpsofactuPE/IPSOFACTU/EMPRESAS/PE/PE"]["files"] == 4
    assert summary["IpsofactuPE/IPSOFACTU/EMPRESAS/PE/PE"]["bytes"] == 3 * 10 + 2
    assert simulation["batchLimited"] is False


def test_nested_quarantine_and_restore_round_trip(tmp_path):
    root = tmp_path / "D"
    _layout(root)
    target = root / "IpsofactuPE" / "IPSOFACTU" / "EMPRESAS" / "PE" / "PE" / "core" / "Log" / "0.log"
    executor = StructuralCleanupExecutor(tmp_path / "agent-data")
    simulation = executor.simulate(
        {"root": str(root), "containerFolder": "core", "targetFolders": ["Log"], "targetFiles": []}
    )

    executor.execute_quarantine(
        {"simulationId": simulation["simulationId"], "manifestHash": simulation["manifestHash"], "executionId": "lote-1"}
    )
    assert not target.exists()
    restored = executor.restore({"root": str(root), "executionId": "lote-1"})
    assert restored["failedCount"] == 0
    assert target.exists()


def test_safety_limit_produces_an_exact_executable_batch(tmp_path):
    root = tmp_path / "D"
    _ipsofactu(root / "Grupo" / "Hotel", logs=7)
    executor = StructuralCleanupExecutor(tmp_path / "agent-data", max_candidates=5)

    simulation = executor.simulate(
        {"root": str(root), "containerFolder": "core", "targetFolders": ["Log"], "targetFiles": FILES}
    )

    assert simulation["eligibleCount"] == 5  # nunca 5 + 1
    assert simulation["batchLimited"] is True
    assert simulation["truncated"] is True
    deleted = executor.execute_direct(
        {"simulationId": simulation["simulationId"], "manifestHash": simulation["manifestHash"]}
    )
    assert deleted["deletedCount"] == 5
    second = executor.simulate(
        {"root": str(root), "containerFolder": "core", "targetFolders": ["Log"], "targetFiles": FILES}
    )
    assert second["eligibleCount"] == 3  # 2 logs + BD_log.txt restantes
    assert second["batchLimited"] is False


def test_simulation_rejects_system_drive_root(tmp_path, monkeypatch):
    from agent.data_express_agent import cleanup as cleanup_module

    monkeypatch.setattr(cleanup_module, "is_system_drive_root", lambda root: True)
    with pytest.raises(CleanupError) as rejected:
        StructuralCleanupExecutor(tmp_path / "agent-data").simulate(
            {"root": str(tmp_path), "targetFolders": ["Log"], "targetFiles": []}
        )
    assert rejected.value.code == "ROOT_TOO_BROAD"
