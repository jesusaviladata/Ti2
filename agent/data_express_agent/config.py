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
    agent_version: str = "0.1.0"
    poll_wait_seconds: int = 25
    request_timeout_seconds: int = 40
    verify_tls: bool = True

    @classmethod
    def from_file(cls, path: Path) -> "AgentConfig":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AgentConfigError("No se pudo leer la configuración del agente") from exc
        try:
            config = cls(
                server_url=str(raw["serverUrl"]).rstrip("/"),
                command_signing_public_key=str(raw["commandSigningPublicKey"]),
                command_signing_key_id=str(raw["commandSigningKeyId"]),
                data_dir=Path(raw.get("dataDir") or default_data_dir()),
                agent_version=str(raw.get("agentVersion", "0.1.0")),
                poll_wait_seconds=int(raw.get("pollWaitSeconds", 25)),
                request_timeout_seconds=int(raw.get("requestTimeoutSeconds", 40)),
                verify_tls=bool(raw.get("verifyTls", True)),
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


def configured_path() -> Path:
    override = os.environ.get("DATAEXPRESS_AGENT_CONFIG")
    return Path(override) if override else default_data_dir() / "agent.json"

