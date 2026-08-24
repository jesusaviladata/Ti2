from __future__ import annotations

import uuid
import threading
import time
from types import SimpleNamespace

from agent.data_express_agent.health import AgentHealthSupervisor
from agent.data_express_agent.journal import ExecutionJournal
from agent.data_express_agent.runner import AgentRunner, retry_delay


class FakeClient:
    def __init__(self, commands=None):
        self.commands = list(commands or [])
        self.completed = []
        self.failed = []
        self.progress_items = []
        self.heartbeats = []
        self.closed = False
        self.config = SimpleNamespace(public_metadata=lambda: {})

    def next_command(self):
        return self.commands.pop(0) if self.commands else None

    def complete(self, command_id, result):
        self.completed.append((command_id, result))

    def fail(self, command_id, code, message):
        self.failed.append((command_id, code, message))

    def progress(self, command_id, value):
        self.progress_items.append((command_id, value))

    def heartbeat(self, metadata, *, health=None, volumes=None):
        self.heartbeats.append({"metadata": metadata, "health": health, "volumes": volumes})

    def close(self):
        self.closed = True


class FakeExplorer:
    def browse_drives(self):
        return {"drives": [{"path": "D:\\"}]}


def _command(command_type="browse_drives"):
    return {
        "id": str(uuid.uuid4()),
        "type": command_type,
        "payload": {},
    }


def test_completed_result_is_journaled_before_reporting_and_can_be_retried(tmp_path):
    command = _command()
    journal = ExecutionJournal(tmp_path / "journal.json")
    first_client = FakeClient([command])
    runner = AgentRunner(first_client, journal, explorer=FakeExplorer())

    runner.run_once()

    assert first_client.completed[0][0] == command["id"]
    journal.entries[command["id"]]["reported"] = False
    journal._save()
    replacement_client = FakeClient()
    AgentRunner(replacement_client, ExecutionJournal(journal.path), explorer=FakeExplorer()).flush_reports()
    assert replacement_client.completed[0][0] == command["id"]


def test_interrupted_destructive_command_never_restarts_automatically(tmp_path):
    command = _command("execute_structural_quarantine")
    journal = ExecutionJournal(tmp_path / "journal.json")
    journal.record_started(command)
    client = FakeClient()

    runner = AgentRunner(client, journal, explorer=FakeExplorer())
    runner.recover_interrupted()
    runner.flush_reports()

    assert client.failed[0][0] == command["id"]
    assert client.failed[0][1] == "MANUAL_REVIEW_REQUIRED"
    assert not client.completed


def test_unknown_command_is_rejected_without_generic_shell_fallback(tmp_path):
    command = _command("run_powershell")
    client = FakeClient([command])
    runner = AgentRunner(
        client, ExecutionJournal(tmp_path / "journal.json"), explorer=FakeExplorer()
    )

    runner.run_once()

    assert client.failed[0][1] == "COMMAND_TYPE_UNSUPPORTED"


def test_file_backup_commands_are_rejected_until_engine_is_enabled(tmp_path):
    command = _command("run_file_backup")
    client = FakeClient([command])
    runner = AgentRunner(
        client, ExecutionJournal(tmp_path / "journal.json"), explorer=FakeExplorer()
    )

    runner.run_once()

    assert client.failed[0][1] == "COMMAND_TYPE_UNSUPPORTED"


def test_enabled_file_engine_receives_only_allowlisted_commands_and_aggregated_progress(tmp_path):
    class FakeFileEngine:
        catalog_revision = 4

        def execute(self, command_type, payload, progress):
            progress(
                {
                    "phase": "copying",
                    "processedUnits": 2,
                    "totalUnits": 5,
                    "foundCount": 5,
                    "details": {"bytesProcessed": 2048},
                }
            )
            return {"status": "completed", "operation": command_type, "payload": payload}

    command = _command("simulate_file_backup")
    command["payload"] = {"taskId": str(uuid.uuid4())}
    client = FakeClient([command])
    runner = AgentRunner(
        client,
        ExecutionJournal(tmp_path / "journal.json"),
        explorer=FakeExplorer(),
        file_backup_executor=FakeFileEngine(),
    )

    runner.run_once()

    assert client.completed[0][1]["operation"] == "simulate_file_backup"
    assert client.progress_items[0][1]["phase"] == "copying"
    assert len(client.progress_items) == 1


def test_interrupted_file_restore_requires_manual_review(tmp_path):
    command = _command("run_file_restore")
    journal = ExecutionJournal(tmp_path / "journal.json")
    journal.record_started(command)
    client = FakeClient()

    runner = AgentRunner(client, journal, explorer=FakeExplorer())
    runner.recover_interrupted()
    runner.flush_reports()

    assert client.failed[0][1] == "MANUAL_REVIEW_REQUIRED"


def test_interrupted_file_backup_resumes_from_verified_checkpoints(tmp_path):
    class FakeFileEngine:
        catalog_revision = 1

        def __init__(self):
            self.operations = []

        def execute(self, command_type, payload, progress):
            self.operations.append(command_type)
            return {"status": "completed", "operation": command_type}

    command = _command("run_file_backup")
    journal = ExecutionJournal(tmp_path / "journal.json")
    journal.record_started(command)
    engine = FakeFileEngine()
    client = FakeClient()

    runner = AgentRunner(
        client,
        journal,
        explorer=FakeExplorer(),
        file_backup_executor=engine,
    )
    runner.recover_interrupted()
    runner.flush_reports()

    assert engine.operations == ["resume_file_backup"]
    assert client.completed[0][1]["operation"] == "resume_file_backup"
    assert not client.failed


def test_retry_delay_is_exponential_bounded_and_jittered():
    assert retry_delay(0, random_value=0.5) == 1.0
    assert retry_delay(3, random_value=0.5) == 8.0
    assert retry_delay(30, random_value=0.5) == 60.0


def test_long_backup_does_not_block_busy_heartbeats(tmp_path):
    class BlockingBackup:
        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()

        def run_batch(self, _payload, progress):
            self.started.set()
            self.release.wait(2)
            return {"status": "completed"}

    command = _command("run_backup_batch")
    client = FakeClient([command])
    backup = BlockingBackup()
    stop = threading.Event()
    health = AgentHealthSupervisor(
        client,
        interval_seconds=0.01,
        metadata_factory=lambda: {"hostname": "CORE-01"},
    )
    runner = AgentRunner(
        client,
        ExecutionJournal(tmp_path / "journal.json"),
        explorer=FakeExplorer(),
        backup_executor=backup,
        health_supervisor=health,
    )
    thread = threading.Thread(target=runner.run_forever, args=(stop,))
    thread.start()
    assert backup.started.wait(1)
    deadline = time.monotonic() + 1
    while len(client.heartbeats) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)

    stop.set()
    backup.release.set()
    thread.join(2)

    assert not thread.is_alive()
    assert len(client.heartbeats) >= 3
    assert any(item["health"]["status"] == "busy" for item in client.heartbeats)
    assert client.closed is True
