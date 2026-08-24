from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .protocol import AgentProtocolError, load_public_key, verify_command


class AgentBootstrapError(ValueError):
    pass


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _validate_control_plane_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise AgentBootstrapError(
            "controlPlaneUrl debe ser un dominio HTTPS sin ruta ni credenciales"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class CommandTrust:
    active_key_id: str
    keys: tuple[tuple[str, str], ...]

    @classmethod
    def from_document(cls, value: Any) -> "CommandTrust":
        try:
            active_key_id = str(value["activeKeyId"]).strip()
            raw_keys = value["keys"]
        except (KeyError, TypeError) as exc:
            raise AgentBootstrapError("La confianza de comandos está incompleta") from exc
        if not active_key_id or len(active_key_id) > 100:
            raise AgentBootstrapError("El identificador de clave activa no es válido")
        keys: list[tuple[str, str]] = []
        seen: set[str] = set()
        for item in raw_keys if isinstance(raw_keys, list) else ():
            try:
                key_id = str(item["keyId"]).strip()
                public_key = str(item["publicKey"]).strip()
                load_public_key(public_key)
            except (KeyError, TypeError, AgentProtocolError) as exc:
                raise AgentBootstrapError("La confianza de comandos contiene una clave inválida") from exc
            if not key_id or len(key_id) > 100 or key_id in seen:
                raise AgentBootstrapError("La confianza de comandos contiene una clave inválida")
            seen.add(key_id)
            keys.append((key_id, public_key))
        if not keys or active_key_id not in seen:
            raise AgentBootstrapError("La clave activa no está incluida en la confianza")
        return cls(active_key_id=active_key_id, keys=tuple(keys))

    def public_key(self, key_id: str | None = None) -> str:
        expected = key_id or self.active_key_id
        for candidate_id, public_key in self.keys:
            if candidate_id == expected:
                return public_key
        raise AgentBootstrapError("La clave solicitada no pertenece a la confianza instalada")

    def apply_signed_rotation(self, document: dict[str, Any]) -> "CommandTrust":
        try:
            signed_by = str(document["signedBy"]).strip()
            signature = str(document["signature"]).strip()
            payload = {
                "schemaVersion": document["schemaVersion"],
                "activeKeyId": document["activeKeyId"],
                "keys": document["keys"],
            }
        except (KeyError, TypeError) as exc:
            raise AgentBootstrapError("La rotación de confianza está incompleta") from exc
        if payload["schemaVersion"] != 1:
            raise AgentBootstrapError("La versión de rotación de confianza no es compatible")
        try:
            verify_command(
                load_public_key(self.public_key(signed_by)),
                signed_by,
                _canonical_json(payload),
                signature,
            )
        except (AgentProtocolError, AgentBootstrapError) as exc:
            raise AgentBootstrapError("La rotación de confianza no tiene una firma válida") from exc
        return CommandTrust.from_document(
            {"activeKeyId": payload["activeKeyId"], "keys": payload["keys"]}
        )


@dataclass(frozen=True, slots=True)
class AgentBootstrap:
    control_plane_url: str
    command_trust: CommandTrust
    agent_version: str
    poll_wait_seconds: int = 25
    request_timeout_seconds: int = 40
    heartbeat_interval_seconds: int = 30

    @classmethod
    def from_file(cls, path: Path) -> "AgentBootstrap":
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            if raw.get("schemaVersion") != 1:
                raise AgentBootstrapError("La versión del bootstrap no es compatible")
            bootstrap = cls(
                control_plane_url=_validate_control_plane_url(
                    str(raw["controlPlaneUrl"])
                ),
                command_trust=CommandTrust.from_document(raw["commandTrust"]),
                agent_version=str(raw["agentVersion"]).strip(),
                poll_wait_seconds=int(raw.get("pollWaitSeconds", 25)),
                request_timeout_seconds=int(raw.get("requestTimeoutSeconds", 40)),
                heartbeat_interval_seconds=int(raw.get("heartbeatIntervalSeconds", 30)),
            )
        except AgentBootstrapError:
            raise
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise AgentBootstrapError("No se pudo leer el bootstrap oficial") from exc
        bootstrap.validate()
        return bootstrap

    def validate(self) -> None:
        _validate_control_plane_url(self.control_plane_url)
        if not self.agent_version or len(self.agent_version) > 32:
            raise AgentBootstrapError("La versión del agente no es válida")
        if not 0 <= self.poll_wait_seconds <= 25:
            raise AgentBootstrapError("pollWaitSeconds debe estar entre 0 y 25")
        if self.request_timeout_seconds < self.poll_wait_seconds + 5:
            raise AgentBootstrapError("requestTimeoutSeconds es demasiado corto")
        if not 10 <= self.heartbeat_interval_seconds <= 120:
            raise AgentBootstrapError(
                "heartbeatIntervalSeconds debe estar entre 10 y 120"
            )


class PairingCodeFile:
    """Reads and clears the one-time code with explicit retry semantics."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> str:
        try:
            code = self.path.read_text(encoding="utf-8-sig").strip()
        except OSError as exc:
            raise AgentBootstrapError("No se pudo abrir el código de vinculación") from exc
        if not code or len(code) > 256:
            raise AgentBootstrapError("El código de vinculación no es válido")
        return code

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)

    def consume(self) -> str:
        code = self.read()
        self.delete()
        return code
