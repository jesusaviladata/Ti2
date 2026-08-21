import threading
import time

from agent.data_express_agent.health import AgentHealthSupervisor


class FakeHealthClient:
    def __init__(self):
        self.config = type("Config", (), {"public_metadata": lambda self: {}})()
        self.heartbeats = []

    def heartbeat(self, metadata, *, health=None, volumes=None):
        self.heartbeats.append(
            {"metadata": metadata, "health": health, "volumes": volumes}
        )


def test_supervisor_keeps_heartbeat_alive_while_operation_is_busy():
    client = FakeHealthClient()
    stop = threading.Event()
    supervisor = AgentHealthSupervisor(
        client,
        interval_seconds=0.01,
        metadata_factory=lambda: {"hostname": "CORE-01"},
    )
    supervisor.begin_operation("run_backup_batch")
    supervisor.start(stop)
    deadline = time.monotonic() + 1
    while len(client.heartbeats) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    stop.set()
    supervisor.stop()

    assert len(client.heartbeats) >= 3
    assert all(item["health"]["status"] == "busy" for item in client.heartbeats)
    assert all(
        item["health"]["currentOperation"] == "run_backup_batch"
        for item in client.heartbeats
    )


def test_health_state_returns_to_connected_after_operation():
    supervisor = AgentHealthSupervisor(FakeHealthClient())
    supervisor.begin_operation("backup")
    supervisor.end_operation()

    assert supervisor.snapshot() == {
        "status": "connected",
        "currentOperation": None,
        "appliedConfigRevision": 0,
    }


def test_file_engine_advertises_capability_and_catalog_revision_only_when_enabled():
    legacy = AgentHealthSupervisor(FakeHealthClient())._default_metadata()
    enabled = AgentHealthSupervisor(
        FakeHealthClient(),
        file_backup_enabled=True,
        catalog_revision_factory=lambda: 7,
    )._default_metadata()

    assert "capabilities" not in legacy
    assert "fileCatalogRevision" not in legacy
    assert enabled["capabilities"] == ["file_backup_v1"]
    assert enabled["fileCatalogRevision"] == 7
