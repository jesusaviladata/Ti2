from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from .backup import BackupError, BackupExecutor
from .dpapi import SecretProtector, WindowsDpapiProtector
from .identity import AgentIdentity
from .secrets import open_secret_envelope


class ProfileApplyError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ManagedProfileStore:
    LEGACY_IMPORT_VERSION = 1
    LEGACY_NAMESPACE = uuid.UUID("2b488c74-2259-4f1f-aa48-5c24b13b1084")
    SECRET_FIELDS = frozenset(
        {"password", "connectionString", "privateKey", "privateKeyPassphrase"}
    )
    LOCAL_ONLY_FIELDS = frozenset({"privateKeyPath"})

    def __init__(
        self,
        path: Path,
        identity: AgentIdentity,
        protector: SecretProtector | None = None,
    ):
        self.path = path
        self.identity = identity
        self.protector = protector or WindowsDpapiProtector()

    def _load_document(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "configRevision": 0, "profiles": {}}
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if document.get("version") != 1 or not isinstance(document.get("profiles"), dict):
                raise ValueError
            return document
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProfileApplyError("PROFILE_STORE_INVALID", "No se pudo abrir la configuración administrada") from exc

    @property
    def config_revision(self) -> int:
        return int(self._load_document().get("configRevision") or 0)

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        revision = int(payload.get("configRevision") or 0)
        document = self._load_document()
        current_revision = int(document.get("configRevision") or 0)
        if revision < current_revision:
            raise ProfileApplyError("PROFILE_REVISION_STALE", "La revisión recibida es anterior a la aplicada")
        if revision == current_revision:
            return {"configRevision": revision, "applied": 0, "status": "unchanged"}
        updates: dict[str, dict] = {}
        for item in payload.get("profiles") or []:
            profile_id = str(uuid.UUID(str(item["id"])))
            profile_type = str(item["profileType"])
            if profile_type not in {"sql", "destination"}:
                raise ProfileApplyError("PROFILE_TYPE_INVALID", "El tipo de perfil no es válido")
            public_config = item.get("publicConfig")
            if not isinstance(public_config, dict):
                raise ProfileApplyError("PROFILE_CONFIG_INVALID", "La configuración pública no es válida")
            existing = dict(document["profiles"].get(profile_id) or {})
            legacy_match_id = None
            if not existing:
                profile_key = str(item.get("profileKey") or profile_id)[:64]
                for candidate_id, candidate in document["profiles"].items():
                    if (
                        candidate.get("legacyImported")
                        and candidate.get("profileType") == profile_type
                        and candidate.get("profileKey") == profile_key
                    ):
                        existing = dict(candidate)
                        legacy_match_id = candidate_id
                        break
            protected_secret = existing.get("protectedSecret")
            envelope = item.get("secretEnvelope")
            if envelope:
                secret = open_secret_envelope(
                    self.identity.encryption_private_key,
                    str(envelope),
                    context=f"{self.identity.agent_id}:{profile_id}".encode("ascii"),
                )
                protected_secret = base64.b64encode(
                    self.protector.protect(
                        json.dumps(secret, separators=(",", ":")).encode("utf-8")
                    )
                ).decode("ascii")
            local_config = {
                key: value
                for key, value in dict(existing.get("localConfig") or {}).items()
                if key in self.LOCAL_ONLY_FIELDS
            }
            updates[profile_id] = {
                "id": profile_id,
                "profileType": profile_type,
                "profileKey": str(item.get("profileKey") or profile_id)[:64],
                "label": str(item.get("label") or profile_id)[:128],
                "publicConfig": public_config,
                "protectedSecret": protected_secret,
                "localConfig": local_config,
                "requiresSecret": bool(existing.get("requiresSecret")) and not protected_secret,
                "desiredRevision": int(item.get("desiredRevision") or 1),
                "isActive": bool(item.get("isActive", True)),
            }
            if legacy_match_id and legacy_match_id != profile_id:
                document["profiles"].pop(legacy_match_id, None)
        next_document = {
            "version": 1,
            "configRevision": revision,
            "profiles": {**document["profiles"], **updates},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(next_document, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            # Re-parse before replacing the last known-good document.
            json.loads(temporary.read_text(encoding="utf-8"))
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        return {"configRevision": revision, "applied": len(updates), "status": "applied"}

    def import_legacy_profiles(
        self,
        sql_instances: tuple[dict, ...],
        backup_destinations: tuple[dict, ...],
    ) -> dict[str, Any]:
        document = self._load_document()
        if int(document.get("legacyImportVersion") or 0) >= self.LEGACY_IMPORT_VERSION:
            return {"status": "unchanged", "imported": 0}
        profiles = dict(document["profiles"])
        imported = 0
        for profile_type, items in (
            ("sql", sql_instances),
            ("destination", backup_destinations),
        ):
            for position, raw in enumerate(items):
                if not isinstance(raw, dict):
                    continue
                profile_key = str(raw.get("profileKey") or raw.get("id") or f"legacy-{position}")[:64]
                label = str(raw.get("label") or profile_key)[:128]
                stable_id = str(
                    uuid.uuid5(
                        self.LEGACY_NAMESPACE,
                        f"{self.identity.installation_id}:{profile_type}:{profile_key}",
                    )
                )
                public_config = {
                    key: value
                    for key, value in raw.items()
                    if key
                    not in {"id", "label", "profileKey"}
                    | self.SECRET_FIELDS
                    | self.LOCAL_ONLY_FIELDS
                }
                local_config = {
                    key: raw[key]
                    for key in self.LOCAL_ONLY_FIELDS
                    if raw.get(key)
                }
                requires_secret = any(raw.get(key) for key in self.SECRET_FIELDS)
                profiles.setdefault(
                    stable_id,
                    {
                        "id": stable_id,
                        "profileType": profile_type,
                        "profileKey": profile_key,
                        "label": label,
                        "publicConfig": public_config,
                        "localConfig": local_config,
                        "protectedSecret": None,
                        "requiresSecret": requires_secret,
                        "desiredRevision": 0,
                        "isActive": True,
                        "legacyImported": True,
                    },
                )
                imported += 1
        next_document = {
            **document,
            "legacyImportVersion": self.LEGACY_IMPORT_VERSION,
            "profiles": profiles,
        }
        self._replace_document(next_document)
        return {"status": "imported", "imported": imported}

    def _replace_document(self, document: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(
                    document,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            json.loads(temporary.read_text(encoding="utf-8"))
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def runtime_profiles(self) -> tuple[tuple[dict, ...], tuple[dict, ...]]:
        document = self._load_document()
        sql: list[dict] = []
        destinations: list[dict] = []
        for item in document["profiles"].values():
            if not item.get("isActive", True):
                continue
            runtime = {
                "id": item["id"],
                "profileKey": item.get("profileKey"),
                "label": item["label"],
                **dict(item.get("publicConfig") or {}),
                **dict(item.get("localConfig") or {}),
                "requiresSecret": bool(item.get("requiresSecret")),
            }
            if item.get("protectedSecret"):
                protected = base64.b64decode(item["protectedSecret"].encode("ascii"), validate=True)
                secret = json.loads(self.protector.unprotect(protected))
                runtime.update(secret)
            (sql if item["profileType"] == "sql" else destinations).append(runtime)
        return tuple(sql), tuple(destinations)

    def public_profiles(self) -> dict[str, list[dict]]:
        sql, destinations = self.runtime_profiles()
        return {
            "sqlInstances": [{"id": item["id"], "label": item["label"]} for item in sql],
            "backupDestinations": [
                {"id": item["id"], "label": item["label"], "type": item.get("type", "")}
                for item in destinations
            ],
        }

    def test_profile(self, profile_id: str) -> dict[str, Any]:
        sql, destinations = self.runtime_profiles()
        for profile in sql:
            if profile["id"] == profile_id:
                databases = BackupExecutor(sql_profiles=(profile,)).list_databases(profile_id)
                return {"profileId": profile_id, "status": "ok", "databaseCount": len(databases["databases"])}
        for profile in destinations:
            if profile["id"] != profile_id:
                continue
            if str(profile.get("type") or "").lower() == "smb":
                root = Path(str(profile.get("path") or ""))
                probe = root / f".dataexpress-probe-{uuid.uuid4().hex}"
                renamed = probe.with_suffix(".verified")
                content = os.urandom(64)
                try:
                    probe.write_bytes(content)
                    if hashlib.sha256(probe.read_bytes()).digest() != hashlib.sha256(content).digest():
                        raise OSError
                    os.replace(probe, renamed)
                    renamed.unlink()
                except OSError as exc:
                    raise ProfileApplyError("DESTINATION_TEST_FAILED", "No se pudo escribir, leer, renombrar y eliminar en el destino") from exc
                return {"profileId": profile_id, "status": "ok", "operations": ["write", "read", "rename", "delete"]}
            if str(profile.get("type") or "").lower() == "sftp":
                # Reuse the production transfer implementation with an isolated probe ZIP.
                raise ProfileApplyError("SFTP_TEST_REQUIRES_APPLY", "Use una ejecución piloto para validar SFTP")
        raise ProfileApplyError("PROFILE_NOT_FOUND", "El perfil no está aplicado en este agente")
