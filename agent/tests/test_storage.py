from collections import namedtuple
from datetime import datetime, timezone

from agent.data_express_agent.storage import StorageCollector, volume_root


Usage = namedtuple("Usage", "total used free")


def test_windows_roots_are_normalized_and_same_drive_is_deduplicated():
    collector = StorageCollector(
        [("D:\\Backups", "backup"), ("D:\\Propiedades", "cleanup")],
        disk_usage=lambda _root: Usage(1000, 400, 600),
        label_provider=lambda _root: "Data",
        now=lambda: datetime(2026, 8, 20, tzinfo=timezone.utc),
    )

    result = collector.collect()

    assert volume_root("D:\\Backups") == "D:\\"
    assert len(result) == 1
    assert result[0]["volumeKey"] == "D:"
    assert result[0]["label"] == "Data"
    assert result[0]["roles"] == ["backup", "cleanup"]
    assert result[0]["freeBytes"] == 600
    assert result[0]["usedPercent"] == 40.0


def test_unreadable_volume_reports_sanitized_unknown_values():
    def inaccessible(_root):
        raise OSError(r"Access denied for \\secret-host\share")

    collector = StorageCollector(
        [(r"\\server\share\backups", "destination")],
        disk_usage=inaccessible,
        label_provider=lambda _root: "",
    )

    result = collector.collect()[0]

    assert result["totalBytes"] is None
    assert result["freeBytes"] is None
    assert result["error"] == "No se pudo leer el volumen"
    assert "secret-host" not in result["error"]
