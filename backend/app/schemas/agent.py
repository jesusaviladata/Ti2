from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class EnrollmentRequest(BaseModel):
    pairing_code: str = Field(alias="pairingCode", min_length=16, max_length=64)
    installation_id: uuid.UUID = Field(alias="installationId")
    hostname: str = Field(min_length=1, max_length=255)
    os_version: str = Field("", alias="osVersion", max_length=255)
    agent_version: str = Field(alias="agentVersion", min_length=1, max_length=50)
    public_key: str = Field(alias="publicKey", min_length=40, max_length=256)

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


class AgentHeartbeatRequest(BaseModel):
    agent_version: str | None = Field(None, alias="agentVersion", max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "forbid"}
