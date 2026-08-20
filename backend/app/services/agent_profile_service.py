from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.agent_protocol import AgentProtocolError, seal_secret_for_agent
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models.operations import AgentConnectionProfile, BackgroundJob, RemoteAgent
from app.repositories.agent_profile_repository import AgentProfileRepository
from app.repositories.agent_repository import AgentRepository
from app.services.agent_command_service import AgentCommandService
from app.services.agent_operation_service import _is_online


PUBLIC_CONFIG_KEYS = {
    "sql": {"server", "driver", "authentication", "backupRoot"},
    "destination": {"type", "path", "host", "port", "username", "hostKeySha256"},
}
SECRET_KEYS = {
    "sql": {"username", "password"},
    "destination": {"password", "privateKey", "privateKeyPassphrase"},
}


def serialize_managed_profile(item: AgentConnectionProfile) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "agentId": str(item.agent_id),
        "profileType": item.profile_type,
        "profileKey": item.profile_key,
        "label": item.label,
        "publicConfig": item.public_config,
        "desiredRevision": item.desired_revision,
        "appliedRevision": item.applied_revision,
        "syncStatus": item.sync_status,
        "lastTestStatus": item.last_test_status,
        "lastTestAt": item.last_test_at.isoformat() if item.last_test_at else None,
        "lastError": item.last_error,
        "hasSecret": bool(item.secret_envelope),
        "isActive": item.is_active,
    }


class AgentProfileService:
    def __init__(
        self,
        db: Any,
        *,
        agents: Any = None,
        profiles: Any = None,
        commands: Any = None,
    ):
        self.db = db
        self.agents = agents or AgentRepository(db)
        self.profiles = profiles or AgentProfileRepository(db)
        self.commands = commands or AgentCommandService(db)

    async def _agent(self, tenant_id: str, agent_id: str) -> RemoteAgent:
        agent = await self.agents.get_agent(tenant_id, agent_id)
        if agent is None:
            raise NotFoundError("Agente")
        if agent.status == "revoked" or agent.revoked_at is not None:
            raise ConflictError("El agente está revocado", code="AGENT_REVOKED")
        return agent

    @staticmethod
    def _validate(profile_type: str, public_config: dict, secret: dict | None) -> None:
        if profile_type not in PUBLIC_CONFIG_KEYS:
            raise DomainError("AGENT_PROFILE_TYPE_INVALID", "Tipo de perfil inválido", 422)
        if set(public_config) - PUBLIC_CONFIG_KEYS[profile_type]:
            raise DomainError(
                "AGENT_PROFILE_CONFIG_INVALID", "La configuración contiene campos no permitidos", 422
            )
        if secret is not None and set(secret) - SECRET_KEYS[profile_type]:
            raise DomainError(
                "AGENT_PROFILE_SECRET_INVALID", "El secreto contiene campos no permitidos", 422
            )
        if profile_type == "sql" and not str(public_config.get("server") or "").strip():
            raise DomainError("AGENT_PROFILE_CONFIG_INVALID", "Indique el servidor SQL", 422)
        if profile_type == "sql" and str(
            public_config.get("authentication") or "windows"
        ).lower() not in {"windows", "windows_integrated"}:
            raise DomainError(
                "AGENT_PROFILE_CONFIG_INVALID",
                "Esta versión solo admite autenticación integrada de Windows",
                422,
            )
        if profile_type == "destination":
            destination_type = str(public_config.get("type") or "").lower()
            if destination_type not in {"smb", "sftp"} or not str(public_config.get("path") or "").strip():
                raise DomainError("AGENT_PROFILE_CONFIG_INVALID", "Indique tipo y ruta del destino", 422)

    @staticmethod
    def _seal(agent: RemoteAgent, profile_id: uuid.UUID, secret: dict | None) -> str | None:
        if secret is None:
            return None
        if not agent.encryption_public_key:
            raise ConflictError(
                "Actualice el agente a 0.4.0 antes de guardar credenciales",
                code="AGENT_ENCRYPTION_KEY_REQUIRED",
            )
        try:
            return seal_secret_for_agent(
                agent.encryption_public_key,
                secret,
                context=f"{agent.id}:{profile_id}".encode("ascii"),
            )
        except AgentProtocolError as exc:
            raise ConflictError(
                "La clave de cifrado del agente no es válida",
                code="AGENT_ENCRYPTION_KEY_INVALID",
            ) from exc

    async def list(self, tenant_id: str, agent_id: str) -> dict:
        agent = await self._agent(tenant_id, agent_id)
        items = await self.profiles.list(tenant_id, agent.id)
        return {
            "agentId": str(agent.id),
            "agentOnline": _is_online(agent),
            "items": [serialize_managed_profile(item) for item in items],
            "total": len(items),
        }

    async def save(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        profile_id: str | None,
        profile_type: str,
        profile_key: str | None,
        label: str,
        public_config: dict,
        secret: dict | None,
    ) -> AgentConnectionProfile:
        agent = await self._agent(tenant_id, agent_id)
        self._validate(profile_type, public_config, secret)
        if profile_id:
            item = await self.profiles.get(tenant_id, agent.id, profile_id)
            if item is None:
                raise NotFoundError("Perfil")
            if item.profile_type != profile_type:
                raise ConflictError("No se puede cambiar el tipo del perfil", code="AGENT_PROFILE_TYPE_IMMUTABLE")
            item.desired_revision += 1
        else:
            item_id = uuid.uuid4()
            item = AgentConnectionProfile(
                id=item_id,
                tenant_id=agent.tenant_id,
                agent_id=agent.id,
                profile_type=profile_type,
                profile_key=(profile_key or str(item_id))[:64],
                desired_revision=1,
                applied_revision=0,
            )
            self.profiles.add(item)
        item.label = label.strip()[:128]
        item.public_config = dict(public_config)
        if secret is not None:
            item.secret_envelope = self._seal(agent, item.id, secret)
        item.sync_status = "pending"
        item.last_error = None
        item.is_active = True
        agent.desired_config_revision = max(
            int(agent.desired_config_revision or 0) + 1,
            item.desired_revision,
        )
        await self.db.flush()
        self._sync_compat_metadata(agent, item)
        await self._queue_apply(agent, item)
        return item

    @staticmethod
    def _sync_compat_metadata(agent: RemoteAgent, item: AgentConnectionProfile) -> None:
        metadata = dict(agent.metadata_json or {})
        field = "sqlInstances" if item.profile_type == "sql" else "backupDestinations"
        profiles = [
            value
            for value in metadata.get(field, []) or []
            if str(value.get("id") or "") != str(item.id)
        ]
        if item.is_active:
            public = {"id": str(item.id), "label": item.label}
            if item.profile_type == "destination":
                public["type"] = str(item.public_config.get("type") or "")
            profiles.append(public)
        metadata[field] = profiles
        agent.metadata_json = metadata

    async def _queue_apply(self, agent: RemoteAgent, item: AgentConnectionProfile) -> None:
        await self.commands.create_command(
            tenant_id=str(agent.tenant_id),
            agent_id=str(agent.id),
            command_type="apply_connection_profiles",
            payload={
                "configRevision": int(agent.desired_config_revision),
                "profiles": [
                    {
                        "id": str(item.id),
                        "profileType": item.profile_type,
                        "profileKey": item.profile_key,
                        "label": item.label,
                        "publicConfig": item.public_config,
                        "secretEnvelope": item.secret_envelope,
                        "desiredRevision": item.desired_revision,
                        "isActive": item.is_active,
                    }
                ],
            },
            idempotency_key=f"apply-profile:{item.id}:{item.desired_revision}",
            ttl_seconds=24 * 60 * 60,
        )

    async def delete(self, tenant_id: str, agent_id: str, profile_id: str) -> None:
        agent = await self._agent(tenant_id, agent_id)
        item = await self.profiles.get(tenant_id, agent.id, profile_id)
        if item is None:
            raise NotFoundError("Perfil")
        item.is_active = False
        item.desired_revision += 1
        item.sync_status = "pending"
        agent.desired_config_revision = int(agent.desired_config_revision or 0) + 1
        self._sync_compat_metadata(agent, item)
        await self._queue_apply(agent, item)

    async def start_job(
        self, tenant_id: str, agent_id: str, *, profile_id: str | None, kind: str
    ) -> BackgroundJob:
        agent = await self._agent(tenant_id, agent_id)
        item = None
        if profile_id:
            item = await self.profiles.get(tenant_id, agent.id, profile_id)
            if item is None or not item.is_active:
                raise NotFoundError("Perfil")
        job = BackgroundJob(
            tenant_id=agent.tenant_id,
            kind=kind,
            status="queued",
            phase="queued",
            resource_id=item.id if item else agent.id,
        )
        self.db.add(job)
        await self.db.flush()
        command_type = "test_connection_profile" if item else "discover_agent_environment"
        payload = {"profileId": str(item.id)} if item else {}
        await self.commands.create_command(
            tenant_id=tenant_id,
            agent_id=agent_id,
            command_type=command_type,
            payload=payload,
            idempotency_key=f"{command_type}:{job.id}",
            job_id=str(job.id),
            ttl_seconds=15 * 60,
        )
        if item:
            item.last_test_status = "testing"
            item.last_test_at = datetime.now(timezone.utc)
        return job
