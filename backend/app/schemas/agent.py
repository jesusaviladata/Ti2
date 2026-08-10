from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class EnrollmentRequest(BaseModel):
    pairing_code: str = Field(alias="pairingCode", min_length=16, max_length=64)
    installation_id: uuid.UUID = Field(alias="installationId")
    hostname: str = Field(min_length=1, max_length=255)
    os_version: str = Field("", alias="osVersion", max_length=255)
    agent_version: str = Field(alias="agentVersion", min_length=1, max_length=50)
    public_key: str = Field(alias="publicKey", min_length=40, max_length=256)

    model_config = {"populate_by_name": True}

