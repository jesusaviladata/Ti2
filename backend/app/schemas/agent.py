from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Literal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


_SENSITIVE_METADATA_KEYS = {
    "accesstoken",
    "apikey",
    "connectionstring",
    "credential",
    "credentials",
    "password",
    "privatekey",
    "pwd",
    "secret",
    "token",
}


def _metadata_contains_secret(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            if normalized in _SENSITIVE_METADATA_KEYS or _metadata_contains_secret(nested):
                return True
    elif isinstance(value, list):
        return any(_metadata_contains_secret(item) for item in value)
    return False


class EnrollmentRequest(BaseModel):
    pairing_code: str = Field(alias="pairingCode", min_length=16, max_length=64)
    installation_id: uuid.UUID = Field(alias="installationId")
    hostname: str = Field(min_length=1, max_length=255)
    os_version: str = Field("", alias="osVersion", max_length=255)
    agent_version: str = Field(alias="agentVersion", min_length=1, max_length=50)
    public_key: str = Field(alias="publicKey", min_length=40, max_length=256)
    encryption_public_key: str | None = Field(
        None, alias="encryptionPublicKey", min_length=40, max_length=128
    )

    model_config = {"populate_by_name": True}


class AgentProgressRequest(BaseModel):
    phase: str = Field(min_length=1, max_length=100)
    processed_units: int = Field(0, alias="processedUnits", ge=0, le=2_000_000_000)
    total_units: int = Field(0, alias="totalUnits", ge=0, le=2_000_000_000)
    found_count: int = Field(0, alias="foundCount", ge=0, le=2_000_000_000)
    database: str | None = Field(None, max_length=255)
    details: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class AgentCompletionRequest(BaseModel):
    result: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class AgentFailureRequest(BaseModel):
    error_code: str = Field(alias="errorCode", min_length=1, max_length=100)
    error_message: str = Field(alias="errorMessage", min_length=1, max_length=1000)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class AgentHealthPayload(BaseModel):
    status: Literal["connected", "busy", "degraded"] = "connected"
    current_operation: str | None = Field(
        None, alias="currentOperation", max_length=80
    )
    applied_config_revision: int = Field(
        0, alias="appliedConfigRevision", ge=0, le=2_000_000_000
    )

    model_config = {"populate_by_name": True, "extra": "forbid"}


class AgentVolumePayload(BaseModel):
    volume_key: str = Field(alias="volumeKey", min_length=1, max_length=128)
    label: str = Field("", max_length=255)
    mount_point: str = Field(alias="mountPoint", min_length=1, max_length=512)
    total_bytes: int | None = Field(None, alias="totalBytes", ge=0)
    free_bytes: int | None = Field(None, alias="freeBytes", ge=0)
    used_percent: float | None = Field(None, alias="usedPercent", ge=0, le=100)
    roles: list[Literal["backup", "cleanup", "destination"]] = Field(
        default_factory=list, max_length=3
    )
    observed_at: datetime = Field(alias="observedAt")
    error: str | None = Field(None, max_length=512)

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def validate_capacity(self):
        if (
            self.total_bytes is not None
            and self.free_bytes is not None
            and self.free_bytes > self.total_bytes
        ):
            raise ValueError("freeBytes no puede exceder totalBytes")
        return self


class AgentHeartbeatRequest(BaseModel):
    agent_version: str | None = Field(None, alias="agentVersion", max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)
    health: AgentHealthPayload | None = None
    volumes: list[AgentVolumePayload] = Field(default_factory=list, max_length=32)

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @field_validator("metadata")
    @classmethod
    def validate_public_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata debe ser serializable como JSON") from exc
        if len(serialized.encode("utf-8")) > 65_536:
            raise ValueError("metadata excede el límite permitido")
        if _metadata_contains_secret(value):
            raise ValueError("metadata solo admite información pública")
        return value
