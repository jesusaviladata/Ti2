from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class AgentConfigError(ValueError):
    pass


def default_data_dir() -> Path:
    program_data = os.environ.get("ProgramData")
    if program_data:
        return Path(program_data) / "DataExpress" / "Agent"
    return Path.home() / ".dataexpress-agent"


@dataclass(frozen=True, slots=True)
class AgentConfig:
    server_url: str
    command_signing_public_key: str
    command_signing_key_id: str
    data_dir: Path
    agent_version: str = "0.2.5"
    poll_wait_seconds: int = 25
    request_timeout_seconds: int = 40
    verify_tls: bool = True
    sql_instances: tuple[dict, ...] = ()
    backup_destinations: tuple[dict, ...] = ()

    @classmethod
    def from_file(cls, path: Path) -> "AgentConfig":
        try:
            # Windows PowerShell 5.1 writes UTF-8 files with a BOM. utf-8-sig
            # accepts those files while remaining compatible with BOM-less UTF-8.
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AgentConfigError("No se pudo leer la configuración del agente") from exc
        try:
            config = cls(
                server_url=str(raw["serverUrl"]).rstrip("/"),
                command_signing_public_key=str(raw["commandSigningPublicKey"]),
                command_signing_key_id=str(raw["commandSigningKeyId"]),
                data_dir=Path(raw.get("dataDir") or default_data_dir()),
                agent_version=str(raw.get("agentVersion", "0.2.5")),
                poll_wait_seconds=int(raw.get("pollWaitSeconds", 25)),
                request_timeout_seconds=int(raw.get("requestTimeoutSeconds", 40)),
                verify_tls=bool(raw.get("verifyTls", True)),
                sql_instances=tuple(raw.get("sqlInstances") or ()),
                backup_destinations=tuple(raw.get("backupDestinations") or ()),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AgentConfigError("La configuración del agente está incompleta") from exc
        config.validate()
        return config

    def validate(self) -> None:
        parsed = urlparse(self.server_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"}:
            raise AgentConfigError("serverUrl debe ser una dirección HTTPS sin ruta")
        if not self.verify_tls:
            raise AgentConfigError("La verificación TLS no puede desactivarse")
        if not self.command_signing_public_key or not self.command_signing_key_id:
            raise AgentConfigError("Falta la clave de verificación de Railway")
        if not 0 <= self.poll_wait_seconds <= 25:
            raise AgentConfigError("pollWaitSeconds debe estar entre 0 y 25")
        if self.request_timeout_seconds < self.poll_wait_seconds + 5:
            raise AgentConfigError("requestTimeoutSeconds es demasiado corto")
        self._validate_profiles(self.sql_instances, "sqlInstances")
        self._validate_profiles(self.backup_destinations, "backupDestinations")

    @staticmethod
    def _validate_profiles(profiles: tuple[dict, ...], field_name: str) -> None:
        identifiers: set[str] = set()
        for profile in profiles:
            if not isinstance(profile, dict):
                raise AgentConfigError(f"{field_name} contiene un perfil invalido")
            identifier = str(profile.get("id") or "").strip()
            label = str(profile.get("label") or "").strip()
            if (
                not identifier
                or not label
                or identifier in identifiers
                or len(identifier) > 64
                or len(label) > 128
            ):
                raise AgentConfigError(f"{field_name} contiene un perfil invalido")
            identifiers.add(identifier)

    def public_metadata(self) -> dict:
        return {
            "sqlInstances": [
                {"id": item["id"], "label": item["label"]}
                for item in self.sql_instances
            ],
            "backupDestinations": [
                {
                    "id": item["id"],
                    "label": item["label"],
                    "type": item.get("type", ""),
                }
                for item in self.backup_destinations
            ],
        }


def configured_path() -> Path:
    override = os.environ.get("DATAEXPRESS_AGENT_CONFIG")
    return Path(override) if override else default_data_dir() / "agent.json"

