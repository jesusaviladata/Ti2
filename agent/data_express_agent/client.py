from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import AgentConfig
from .bootstrap import CommandTrust
from .identity import AgentIdentity
from .protocol import AgentProtocolError, load_public_key, sign_request, verify_command


class AgentClientError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        recoverable: bool = False,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable
        self.status_code = status_code


def canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class AgentClient:
    def __init__(
        self,
        config: AgentConfig,
        identity: AgentIdentity,
        *,
        transport: httpx.BaseTransport | None = None,
        command_trust: CommandTrust | None = None,
    ):
        self.config = config
        self.identity = identity
        self.http = httpx.Client(
            base_url=config.server_url,
            verify=config.verify_tls,
            timeout=config.request_timeout_seconds,
            transport=transport,
            follow_redirects=False,
        )
        self._legacy_heartbeat = False
        self.command_trust = command_trust
        self.command_public_keys = {
            key_id: load_public_key(public_key)
            for key_id, public_key in (
                command_trust.keys
                if command_trust is not None
                else ((config.command_signing_key_id, config.command_signing_public_key),)
            )
        }

    def close(self) -> None:
        self.http.close()

    def enroll(
        self,
        pairing_code: str,
        *,
        hostname: str,
        os_version: str,
    ) -> None:
        body = canonical_json(
            {
                "pairingCode": pairing_code,
                "installationId": self.identity.installation_id,
                "hostname": hostname,
                "osVersion": os_version,
                "agentVersion": self.config.agent_version,
                "publicKey": self.identity.public_key,
                "encryptionPublicKey": self.identity.encryption_public_key,
            }
        )
        try:
            response = self.http.post(
                "/agent/v1/enroll",
                content=body,
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise AgentClientError(
                "NETWORK_UNAVAILABLE",
                "No fue posible contactar a Railway",
                recoverable=True,
            ) from exc
        if response.status_code != 201:
            raise AgentClientError(
                "ENROLLMENT_REJECTED", "Railway rechazó la vinculación"
            )
        try:
            result = response.json()
            if result["commandSigningKeyId"] != self.config.command_signing_key_id:
                raise ValueError
            self.identity.agent_id = result["agentId"]
            self.identity.tenant_id = result["tenantId"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AgentClientError(
                "ENROLLMENT_RESPONSE_INVALID", "Railway devolvió una respuesta inválida"
            ) from exc

    def heartbeat(
        self,
        metadata: dict[str, Any],
        *,
        health: dict[str, Any] | None = None,
        volumes: list[dict[str, Any]] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "agentVersion": self.config.agent_version,
            "metadata": metadata,
        }
        if not self._legacy_heartbeat:
            payload["encryptionPublicKey"] = self.identity.encryption_public_key
        if health is not None and not self._legacy_heartbeat:
            payload["health"] = health
        if volumes is not None and not self._legacy_heartbeat:
            payload["volumes"] = volumes
        try:
            self._request("POST", "/agent/v1/heartbeat", payload)
        except AgentClientError as exc:
            if exc.status_code != 422 or self._legacy_heartbeat:
                raise
            legacy_payload = {
                "agentVersion": self.config.agent_version,
                "metadata": metadata,
            }
            self._request("POST", "/agent/v1/heartbeat", legacy_payload)
            self._legacy_heartbeat = True

    def next_command(self) -> dict[str, Any] | None:
        path = f"/agent/v1/commands/next?wait={self.config.poll_wait_seconds}"
        response = self._request("GET", path)
        if response.status_code == 204:
            return None
        key_id = response.headers.get("X-Command-Key-Id", "")
        signature = response.headers.get("X-Command-Signature", "")
        command_public_key = self.command_public_keys.get(key_id)
        if command_public_key is None:
            raise AgentClientError(
                "COMMAND_SIGNATURE_INVALID", "La orden no tiene una firma válida"
            )
        try:
            verify_command(command_public_key, key_id, response.content, signature)
            command = response.json()
            self._validate_command(command)
            return command
        except (AgentProtocolError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AgentClientError(
                "COMMAND_SIGNATURE_INVALID", "La orden no tiene una firma válida"
            ) from exc

    def progress(self, command_id: str, progress: dict[str, Any]) -> None:
        # Only the typed progress contract is forwarded. Database and details
        # let Railway persist the validated .bak before ZIP/delivery finishes.
        payload = {
            key: progress[key]
            for key in (
                "phase",
                "processedUnits",
                "totalUnits",
                "foundCount",
                "database",
                "details",
            )
            if key in progress
        }
        self._request(
            "POST", f"/agent/v1/commands/{command_id}/progress", payload
        )

    def complete(self, command_id: str, result: dict[str, Any]) -> None:
        self._request(
            "POST", f"/agent/v1/commands/{command_id}/complete", {"result": result}
        )

    def fail(self, command_id: str, error_code: str, error_message: str) -> None:
        self._request(
            "POST",
            f"/agent/v1/commands/{command_id}/fail",
            {"errorCode": error_code, "errorMessage": error_message},
        )

    def _request(
        self,
        method: str,
        path_with_query: str,
        value: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if not self.identity.agent_id:
            raise AgentClientError("AGENT_NOT_ENROLLED", "El agente no está vinculado")
        body = canonical_json(value) if value is not None else b""
        timestamp = int(time.time())
        nonce = secrets.token_urlsafe(24)
        signature = sign_request(
            self.identity.private_key,
            method=method,
            path_with_query=path_with_query,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        )
        headers = {
            "X-Agent-Id": self.identity.agent_id,
            "X-Agent-Timestamp": str(timestamp),
            "X-Agent-Nonce": nonce,
            "X-Agent-Signature": signature,
        }
        if value is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = self.http.request(
                method, path_with_query, content=body, headers=headers
            )
        except httpx.HTTPError as exc:
            raise AgentClientError(
                "NETWORK_UNAVAILABLE",
                "No fue posible contactar a Railway",
                recoverable=True,
            ) from exc
        if response.status_code not in {200, 204}:
            recoverable = response.status_code >= 500 or response.status_code == 429
            raise AgentClientError(
                "AGENT_REQUEST_REJECTED",
                f"Railway rechazó la solicitud ({response.status_code})",
                recoverable=recoverable,
                status_code=response.status_code,
            )
        return response

    def _validate_command(self, command: dict[str, Any]) -> None:
        required = {
            "id",
            "agentId",
            "tenantId",
            "type",
            "payload",
            "issuedAt",
            "expiresAt",
            "idempotencyKey",
        }
        if not required.issubset(command) or command["agentId"] != self.identity.agent_id:
            raise ValueError
        if command["tenantId"] != self.identity.tenant_id:
            raise ValueError
        expiration = datetime.fromisoformat(command["expiresAt"].replace("Z", "+00:00"))
        if expiration <= datetime.now(timezone.utc):
            raise ValueError

