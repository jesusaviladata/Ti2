from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.agent_protocol import (
    AgentProtocolError,
    load_public_key,
    public_key_to_base64,
)
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models.operations import AgentPairingToken, RemoteAgent
from app.repositories.agent_repository import AgentRepository
from app.repositories.cleanup_repository import tenant_uuid


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentEnrollmentService:
    def __init__(
        self,
        db: Any,
        *,
        repo: AgentRepository | Any | None = None,
        enrollment_ttl_seconds: int = 600,
    ):
        self.db = db
        self.repo = repo or AgentRepository(db)
        self.enrollment_ttl_seconds = enrollment_ttl_seconds

    @staticmethod
    def normalize_pairing_code(code: str) -> str:
        return "".join(character for character in code.upper() if character.isalnum())

    @classmethod
    def hash_pairing_code(cls, code: str) -> str:
        normalized = cls.normalize_pairing_code(code)
        return hashlib.sha256(normalized.encode("ascii")).hexdigest()

    @staticmethod
    def _new_pairing_code() -> str:
        raw = base64.b32encode(secrets.token_bytes(16)).decode("ascii").rstrip("=")
        return "-".join((raw[:7], raw[7:14], raw[14:20], raw[20:]))

    async def issue_pairing_code(
        self,
        tenant_id: str,
        user_id: str,
        replace_agent_id: str | None = None,
    ) -> dict[str, str]:
        if replace_agent_id:
            old_agent = await self.repo.get_agent(tenant_id, replace_agent_id)
            if old_agent is None:
                raise NotFoundError("Agente")
        code = self._new_pairing_code()
        expires_at = _utcnow() + timedelta(seconds=self.enrollment_ttl_seconds)
        pairing = AgentPairingToken(
            tenant_id=tenant_uuid(tenant_id),
            token_hash=self.hash_pairing_code(code),
            expires_at=expires_at,
            created_by=uuid.UUID(user_id),
            replace_agent_id=uuid.UUID(replace_agent_id) if replace_agent_id else None,
        )
        self.db.add(pairing)
        await self.db.flush()
        return {"code": code, "expiresAt": expires_at.isoformat()}

    @staticmethod
    def _invalid_enrollment() -> DomainError:
        return DomainError(
            "AGENT_ENROLLMENT_INVALID",
            "No fue posible vincular el agente",
            401,
        )

    async def enroll(
        self,
        pairing_code: str,
        *,
        installation_id: str,
        hostname: str,
        os_version: str,
        agent_version: str,
        public_key: str,
    ) -> RemoteAgent:
        try:
            canonical_public_key = public_key_to_base64(load_public_key(public_key))
            uuid.UUID(installation_id)
        except (AgentProtocolError, ValueError):
            raise self._invalid_enrollment()

        pairing = await self.repo.get_pairing_for_update(
            self.hash_pairing_code(pairing_code)
        )
        now = _utcnow()
        if (
            pairing is None
            or pairing.used_at is not None
            or pairing.expires_at <= now
        ):
            raise self._invalid_enrollment()

        tenant_id = str(pairing.tenant_id)
        duplicate = await self.repo.get_by_installation(tenant_id, installation_id)
        if duplicate is not None and duplicate.status != "revoked":
            raise ConflictError(
                "Esta instalación ya está vinculada",
                code="AGENT_ALREADY_ENROLLED",
            )

        old_agent = None
        if pairing.replace_agent_id:
            old_agent = await self.repo.get_agent(
                tenant_id, str(pairing.replace_agent_id)
            )
            if old_agent is None or old_agent.revoked_at is not None:
                raise self._invalid_enrollment()

        agent = RemoteAgent(
            tenant_id=pairing.tenant_id,
            installation_id=installation_id,
            hostname=hostname.strip(),
            os_version=os_version.strip(),
            agent_version=agent_version.strip(),
            public_key=canonical_public_key,
            status="connected",
            last_seen_at=now,
            metadata_json={},
        )
        self.db.add(agent)
        await self.db.flush()
        pairing.used_at = now
        if old_agent is not None:
            old_agent.status = "revoked"
            old_agent.revoked_at = now
            old_agent.replaced_by_id = agent.id
        return agent

    async def list_agents(self, tenant_id: str) -> list[RemoteAgent]:
        return await self.repo.list_agents(tenant_id)

    async def revoke(self, tenant_id: str, agent_id: str) -> RemoteAgent:
        agent = await self.repo.get_agent(tenant_id, agent_id)
        if agent is None:
            raise NotFoundError("Agente")
        if agent.revoked_at is None:
            agent.revoked_at = _utcnow()
            agent.status = "revoked"
        await self.db.flush()
        return agent

