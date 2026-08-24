from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import PureWindowsPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.file_backup import (
    FileBackupFilterKind,
    FileBackupFilterOperator,
    FileBackupFormat,
    FileBackupRunStatus,
    FileBackupStrategy,
    FileRestoreStatus,
)


_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_UNC_PATH = re.compile(r"^\\\\[^\\/]+\\[^\\/]+(?:\\.*)?$")


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(word[:1].upper() + word[1:] for word in rest)


def _absolute_windows_path(value: str) -> str:
    normalized = value.strip()
    if not normalized or "\x00" in normalized:
        raise ValueError("La ruta no es válida")
    if normalized.startswith(("\\\\?\\", "\\\\.\\")):
        raise ValueError("No se permiten rutas de dispositivo")
    if not (_DRIVE_PATH.match(normalized) or _UNC_PATH.match(normalized)):
        raise ValueError("Se requiere una ruta absoluta de Windows o UNC completa")
    return normalized


class FileBackupSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
        use_enum_values=False,
    )


class FileBackupSourceInput(FileBackupSchema):
    path: str = Field(min_length=3, max_length=2048)
    include_subfolders: bool = True

    _validate_path = field_validator("path")(_absolute_windows_path)


class FileBackupFilterInput(FileBackupSchema):
    kind: FileBackupFilterKind
    operator: FileBackupFilterOperator
    pattern: str = Field(min_length=1, max_length=1024)
    is_enabled: bool = True

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or "\x00" in normalized:
            raise ValueError("El patrón no es válido")
        return normalized


class FileBackupScheduleInput(FileBackupSchema):
    weekdays: list[int] = Field(min_length=1, max_length=7)
    local_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("Los días deben estar entre 0 y 6")
        return sorted(set(value))


class FileBackupTaskCreate(FileBackupSchema):
    name: str = Field(min_length=1, max_length=255)
    agent_id: uuid.UUID
    destination_profile_id: uuid.UUID
    sources: list[FileBackupSourceInput] = Field(min_length=1, max_length=64)
    filters: list[FileBackupFilterInput] = Field(default_factory=list, max_length=200)
    strategy: FileBackupStrategy = FileBackupStrategy.full
    format: FileBackupFormat = FileBackupFormat.direct
    schedule: FileBackupScheduleInput
    timezone_name: str = Field("America/Mexico_City", min_length=1, max_length=64)
    missed_run_policy: Literal["run_once", "skip"] = "run_once"
    retention_full_chains: int = Field(4, ge=1, le=100)
    vss_policy: Literal["required", "preferred", "disabled"] = "preferred"
    verification_mode: Literal["sha256"] = "sha256"
    is_active: bool = True

    @field_validator("name", "timezone_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("El valor no puede quedar vacío")
        return normalized


class FileBackupTaskUpdate(FileBackupSchema):
    name: str | None = Field(None, min_length=1, max_length=255)
    destination_profile_id: uuid.UUID | None = None
    sources: list[FileBackupSourceInput] | None = Field(None, min_length=1, max_length=64)
    filters: list[FileBackupFilterInput] | None = Field(None, max_length=200)
    strategy: FileBackupStrategy | None = None
    format: FileBackupFormat | None = None
    schedule: FileBackupScheduleInput | None = None
    timezone_name: str | None = Field(None, min_length=1, max_length=64)
    missed_run_policy: Literal["run_once", "skip"] | None = None
    retention_full_chains: int | None = Field(None, ge=1, le=100)
    vss_policy: Literal["required", "preferred", "disabled"] | None = None
    verification_mode: Literal["sha256"] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("Indique al menos un cambio")
        return self


class FileBackupTaskResponse(FileBackupTaskCreate):
    id: uuid.UUID
    tenant_id: uuid.UUID
    config_revision: int = Field(ge=1)
    first_run_will_be_full: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FileBackupTaskPage(FileBackupSchema):
    items: list[FileBackupTaskResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class FileBackupSimulationResponse(FileBackupSchema):
    id: uuid.UUID
    task_id: uuid.UUID
    status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class FileBackupRunCreate(FileBackupSchema):
    strategy: FileBackupStrategy | None = None


class FileBackupRunResponse(FileBackupSchema):
    id: uuid.UUID
    task_id: uuid.UUID
    agent_id: uuid.UUID
    status: FileBackupRunStatus
    strategy: FileBackupStrategy
    phase: str
    progress_percent: int = Field(ge=0, le=100)
    files_total: int | None = Field(None, ge=0)
    files_processed: int = Field(0, ge=0)
    bytes_total: int | None = Field(None, ge=0)
    bytes_processed: int = Field(0, ge=0)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FileBackupRunPage(FileBackupSchema):
    items: list[FileBackupRunResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class FileRestoreCreate(FileBackupSchema):
    chain_id: uuid.UUID
    agent_id: uuid.UUID
    destination_mode: Literal["original", "alternate"]
    destination_path: str | None = Field(None, max_length=2048)
    selections: list[str] = Field(min_length=1, max_length=5000)

    @field_validator("selections")
    @classmethod
    def validate_selections(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = value.strip()
            path = PureWindowsPath(candidate)
            if (
                not candidate
                or path.is_absolute()
                or any(part in {".", ".."} for part in path.parts)
            ):
                raise ValueError("La selección debe ser una ruta relativa segura")
            normalized.append(candidate)
        return normalized

    @model_validator(mode="after")
    def validate_destination(self):
        if self.destination_mode == "alternate":
            if self.destination_path is None:
                raise ValueError("La restauración alternativa requiere destino")
            self.destination_path = _absolute_windows_path(self.destination_path)
        elif self.destination_path is not None:
            self.destination_path = _absolute_windows_path(self.destination_path)
        return self


class FileRestoreResponse(FileBackupSchema):
    id: uuid.UUID
    chain_id: uuid.UUID
    agent_id: uuid.UUID
    status: FileRestoreStatus
    destination_mode: Literal["original", "alternate"]
    destination_path: str
    selection_summary: dict[str, Any] = Field(default_factory=dict)
    simulation_summary: dict[str, Any] = Field(default_factory=dict)
    simulation_hash: str | None = Field(None, min_length=64, max_length=64)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime


class FileRestoreConfirmationCreate(FileBackupSchema):
    simulation_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class FileBackupArtifactPatch(FileBackupSchema):
    protected: bool


class FileBackupArtifactResponse(FileBackupSchema):
    id: uuid.UUID
    protected: bool
    protected_at: datetime | None = None
    protected_by: uuid.UUID | None = None


class FileBackupChainResponse(FileBackupSchema):
    id: uuid.UUID
    task_id: uuid.UUID
    status: str
    full_started_at: datetime | None = None
    latest_run_at: datetime | None = None
    created_at: datetime
