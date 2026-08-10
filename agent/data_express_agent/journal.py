from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class ExecutionJournal:
    def __init__(self, path: Path, *, max_entries: int = 2000):
        self.path = path
        self.max_entries = max_entries
        self.entries: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if document.get("version") == 1 and isinstance(document.get("entries"), dict):
                self.entries = document["entries"]
        except (OSError, json.JSONDecodeError, TypeError):
            self.entries = {}

    def get(self, command_id: str) -> dict[str, Any] | None:
        return self.entries.get(command_id)

    def record_started(self, command: dict[str, Any]) -> None:
        command_id = command["id"]
        self.entries[command_id] = {
            "status": "started",
            "command": command,
            "reported": False,
        }
        self._save()

    def record_completed(self, command_id: str, result: dict[str, Any]) -> None:
        entry = self.entries[command_id]
        entry.update({"status": "completed", "result": result, "reported": False})
        self._save()

    def record_failed(self, command_id: str, code: str, message: str) -> None:
        entry = self.entries[command_id]
        entry.update(
            {
                "status": "failed",
                "errorCode": code,
                "errorMessage": message,
                "reported": False,
            }
        )
        self._save()

    def mark_reported(self, command_id: str) -> None:
        if command_id in self.entries:
            self.entries[command_id]["reported"] = True
            self._save()

    def unreported(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            (command_id, entry)
            for command_id, entry in self.entries.items()
            if entry.get("status") in {"completed", "failed"}
            and not entry.get("reported")
        ]

    def interrupted(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            (command_id, entry)
            for command_id, entry in self.entries.items()
            if entry.get("status") == "started"
        ]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if len(self.entries) > self.max_entries:
            removable = [key for key, value in self.entries.items() if value.get("reported")]
            for key in removable[: len(self.entries) - self.max_entries]:
                self.entries.pop(key, None)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {"version": 1, "entries": self.entries},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

