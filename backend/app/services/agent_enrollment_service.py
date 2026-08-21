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
from app.models.operations import AgentPairingToken, AgentReplacementSession, RemoteAgent
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
        replacement_session_id: str | None = None,
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
            replacement_session_id=(
                uuid.UUID(replacement_session_id)
                if replacement_session_id
                else None
            ),
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

    @classmethod
    def _canonical_encryption_public_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            raw = base64.b64decode(value.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError) as exc:
            raise cls._invalid_enrollment() from exc
        if len(raw) != 32:
            raise cls._invalid_enrollment()
        return base64.b64encode(raw).decode("ascii")

    async def enroll(
        self,
        pairing_code: str,
        *,
        installation_id: str,
        hostname: str,
        os_version: str,
        agent_version: str,
        public_key: str,
        encryption_public_key: str | None = None,
    ) -> RemoteAgent:
        try:
            canonical_public_key = public_key_to_base64(load_public_key(public_key))
            uuid.UUID(installation_id)
        except (AgentProtocolError, ValueError):
            raise self._invalid_enrollment()
        canonical_encryption_public_key = self._canonical_encryption_public_key(
            encryption_public_key
        )

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
        replacement_session: AgentReplacementSession | None = None
        if pairing.replace_agent_id:
            old_agent = await self.repo.get_agent(
                tenant_id, str(pairing.replace_agent_id)
            )
            if old_agent is None or old_agent.revoked_at is not None:
                raise self._invalid_enrollment()
        if pairing.replacement_session_id:
            replacement_session = await self.repo.get_replacement_session(
                tenant_id,
                str(pairing.replacement_session_id),
                for_update=True,
            )
            if (
                replacement_session is None
                or replacement_session.status != "awaiting_candidate"
                or replacement_session.expires_at <= now
                or replacement_session.candidate_agent_id is not None
                or replacement_session.old_agent_id != pairing.replace_agent_id
            ):
                raise self._invalid_enrollment()

        agent_id = uuid.uuid4()
        agent = RemoteAgent(
            id=agent_id,
            tenant_id=pairing.tenant_id,
            installation_id=installation_id,
            hostname=hostname.strip(),
            os_version=os_version.strip(),
            agent_version=agent_version.strip(),
            public_key=canonical_public_key,
            encryption_public_key=canonical_encryption_public_key,
            status=(
                "replacement_pending" if old_agent is not None else "connected"
            ),
            last_seen_at=now,
            metadata_json={},
            lineage_id=(
                (old_agent.lineage_id or old_agent.id)
                if old_agent is not None
                else agent_id
            ),
        )
        self.db.add(agent)
        await self.db.flush()
        pairing.used_at = now
        if old_agent is not None:
            if replacement_session is None:
                replacement_session = AgentReplacementSession(
                    tenant_id=pairing.tenant_id,
                    old_agent_id=old_agent.id,
                    candidate_agent_id=agent.id,
                    status="awaiting_confirmation",
                    expected_old_revision=int(old_agent.desired_config_revision or 0),
                    created_by=pairing.created_by,
                    expires_at=pairing.expires_at,
                    audit_json={"legacyPairingTokenId": str(pairing.id)},
                )
                self.db.add(replacement_session)
            else:
                replacement_session.candidate_agent_id = agent.id
                replacement_session.status = "awaiting_confirmation"
                replacement_session.audit_json = {
                    **dict(replacement_session.audit_json or {}),
                    "candidateEnrolledAt": now.isoformat(),
                }
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
