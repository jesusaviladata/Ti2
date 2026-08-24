from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.errors import ConflictError, NotFoundError
from app.models.operations import AgentConnectionProfile, AgentReplacementSession
from app.repositories.agent_repository import AgentRepository
from app.repositories.cleanup_repository import tenant_uuid
from app.services.agent_enrollment_service import AgentEnrollmentService
from app.services.agent_command_service import AgentCommandService


ACTIVE_SESSION_STATES = {"awaiting_candidate", "awaiting_confirmation"}
TERMINAL_SESSION_STATES = {"completed", "cancelled", "expired"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentReplacementService:
    def __init__(
        self,
        db: Any,
        *,
        repo: Any | None = None,
        enrollment: Any | None = None,
        commands: Any | None = None,
        ttl_seconds: int = 600,
        healthy_within_seconds: int = 120,
        now=None,
    ):
        self.db = db
        self.repo = repo or AgentRepository(db)
        self.enrollment = enrollment or AgentEnrollmentService(
            db,
            repo=self.repo,
            enrollment_ttl_seconds=ttl_seconds,
        )
        self.commands = commands or AgentCommandService(db, repo=self.repo)
        self.ttl_seconds = ttl_seconds
        self.healthy_within_seconds = healthy_within_seconds
        self.now = now or _utcnow

    async def create(
        self, tenant_id: str, old_agent_id: str, user_id: str
    ) -> dict[str, Any]:
        old = await self.repo.get_agent(tenant_id, old_agent_id)
        if old is None:
            raise NotFoundError("Agente")
        if old.status == "revoked" or old.revoked_at is not None:
            raise ConflictError("El agente está revocado", code="AGENT_REVOKED")
        existing = await self.repo.get_open_replacement_for_old(tenant_id, old.id)
        if existing is not None:
            raise ConflictError(
                "Ya existe un reemplazo pendiente para este agente",
                code="AGENT_REPLACEMENT_ALREADY_OPEN",
            )
        expires_at = self.now() + timedelta(seconds=self.ttl_seconds)
        session = AgentReplacementSession(
            tenant_id=tenant_uuid(tenant_id),
            old_agent_id=old.id,
            status="awaiting_candidate",
            expected_old_revision=int(old.desired_config_revision or 0),
            created_by=uuid.UUID(user_id),
            expires_at=expires_at,
            audit_json={"createdAt": self.now().isoformat()},
        )
        self.db.add(session)
        await self.db.flush()
        pairing = await self.enrollment.issue_pairing_code(
            tenant_id,
            user_id,
            replace_agent_id=str(old.id),
            replacement_session_id=str(session.id),
        )
        result = await self._serialize(tenant_id, session, old=old)
        result["code"] = pairing["code"]
        return result

    async def get(self, tenant_id: str, session_id: str) -> dict[str, Any]:
        session = await self._session(tenant_id, session_id)
        await self._expire_if_needed(tenant_id, session)
        return await self._serialize(tenant_id, session)

    async def confirm(
        self, tenant_id: str, session_id: str, user_id: str
    ) -> dict[str, Any]:
        session = await self._session(tenant_id, session_id, for_update=True)
        if session.status == "completed":
            return await self._serialize(tenant_id, session)
        if session.status in {"cancelled", "expired"}:
            raise ConflictError(
                "La sesión de reemplazo ya terminó",
                code="AGENT_REPLACEMENT_FINALIZED",
            )
        await self._expire_if_needed(tenant_id, session)
        if session.status == "expired":
            raise ConflictError(
                "La sesión de reemplazo expiró",
                code="AGENT_REPLACEMENT_EXPIRED",
            )
        old = await self.repo.get_agent(tenant_id, str(session.old_agent_id))
        candidate = (
            await self.repo.get_agent(tenant_id, str(session.candidate_agent_id))
            if session.candidate_agent_id
            else None
        )
        blockers = await self._blockers(tenant_id, session, old, candidate)
        if blockers:
            raise ConflictError(
                "El reemplazo todavía no puede confirmarse: " + ", ".join(blockers),
                code="AGENT_REPLACEMENT_NOT_READY",
            )
        assert old is not None and candidate is not None
        profile_map, requiring_secret, ready_profiles = await self._clone_profiles(
            tenant_id, old.id, candidate.id
        )
        await self.db.flush()
        plans = await self.repo.list_agent_backup_plans(tenant_id, old.id)
        for plan in plans:
            plan.agent_id = candidate.id
            plan.sql_profile_id = profile_map.get(
                str(plan.sql_profile_id), plan.sql_profile_id
            )
            if plan.destination_profile_id:
                plan.destination_profile_id = profile_map.get(
                    str(plan.destination_profile_id), plan.destination_profile_id
                )
        tasks = await self.repo.list_file_backup_tasks(tenant_id, old.id)
        for task in tasks:
            task.agent_id = candidate.id
            task.destination_profile_id = uuid.UUID(
                profile_map.get(
                    str(task.destination_profile_id), str(task.destination_profile_id)
                )
            )
            task.config_revision += 1
            task.updated_at = self.now()
        server = await self.repo.get_remote_server_for_agent(tenant_id, old.id)
        if server is not None:
            server.agent_id = candidate.id
            server.config_revision += 1
        lineage_id = old.lineage_id or old.id
        old.lineage_id = lineage_id
        candidate.lineage_id = lineage_id
        old.status = "revoked"
        old.revoked_at = self.now()
        old.replaced_by_id = candidate.id
        candidate.status = "connected"
        candidate.desired_config_revision = max(
            int(candidate.desired_config_revision or 0),
            int(old.desired_config_revision or 0),
        )
        if ready_profiles:
            await self.commands.create_command(
                tenant_id=tenant_id,
                agent_id=str(candidate.id),
                command_type="apply_connection_profiles",
                payload={
                    "configRevision": int(candidate.desired_config_revision or 0),
                    "profiles": [
                        {
                            "id": str(item.id),
                            "profileType": item.profile_type,
                            "profileKey": item.profile_key,
                            "label": item.label,
                            "publicConfig": item.public_config,
                            "secretEnvelope": None,
                            "desiredRevision": item.desired_revision,
                            "isActive": item.is_active,
                        }
                        for item in ready_profiles
                    ],
                },
                idempotency_key=f"replacement-profiles:{session.id}",
                ttl_seconds=24 * 60 * 60,
            )
        session.status = "completed"
        session.confirmed_at = self.now()
        session.audit_json = {
            **dict(session.audit_json or {}),
            "confirmedAt": session.confirmed_at.isoformat(),
            "confirmedBy": user_id,
            "profilesTransferred": len(profile_map),
            "profilesRequiringSecret": requiring_secret,
            "plansTransferred": len(plans),
            "fileTasksTransferred": len(tasks),
        }
        await self.db.flush()
        return await self._serialize(tenant_id, session, old=old, candidate=candidate)

    async def cancel(
        self, tenant_id: str, session_id: str, user_id: str
    ) -> dict[str, Any]:
        session = await self._session(tenant_id, session_id, for_update=True)
        if session.status in {"cancelled", "expired"}:
            return await self._serialize(tenant_id, session)
        if session.status == "completed":
            raise ConflictError(
                "El reemplazo ya fue confirmado",
                code="AGENT_REPLACEMENT_FINALIZED",
            )
        candidate = (
            await self.repo.get_agent(tenant_id, str(session.candidate_agent_id))
            if session.candidate_agent_id
            else None
        )
        if candidate is not None:
            candidate.status = "revoked"
            candidate.revoked_at = self.now()
        session.status = "cancelled"
        session.cancelled_at = self.now()
        session.audit_json = {
            **dict(session.audit_json or {}),
            "cancelledAt": session.cancelled_at.isoformat(),
            "cancelledBy": user_id,
        }
        await self.db.flush()
        return await self._serialize(tenant_id, session, candidate=candidate)

    async def _session(
        self, tenant_id: str, session_id: str, *, for_update: bool = False
    ) -> AgentReplacementSession:
        session = await self.repo.get_replacement_session(
            tenant_id, session_id, for_update=for_update
        )
        if session is None:
            raise NotFoundError("Sesión de reemplazo")
        return session

    async def _expire_if_needed(
        self, tenant_id: str, session: AgentReplacementSession
    ) -> None:
        if session.status not in ACTIVE_SESSION_STATES or session.expires_at > self.now():
            return
        candidate = (
            await self.repo.get_agent(tenant_id, str(session.candidate_agent_id))
            if session.candidate_agent_id
            else None
        )
        if candidate is not None:
            candidate.status = "revoked"
            candidate.revoked_at = self.now()
        session.status = "expired"
        session.cancelled_at = self.now()
        session.audit_json = {
            **dict(session.audit_json or {}),
            "expiredAt": self.now().isoformat(),
        }
        await self.db.flush()

    async def _blockers(self, tenant_id, session, old, candidate) -> list[str]:
        blockers: list[str] = []
        if old is None or old.status == "revoked" or old.revoked_at is not None:
            blockers.append("agente anterior no disponible")
        elif int(old.desired_config_revision or 0) != session.expected_old_revision:
            blockers.append("la configuración anterior cambió")
        if candidate is None or candidate.status != "replacement_pending":
            blockers.append("candidato no vinculado")
        else:
            last = candidate.last_heartbeat_at or candidate.last_seen_at
            if (
                last is None
                or last < self.now() - timedelta(seconds=self.healthy_within_seconds)
                or candidate.health_status not in {"connected", "busy", "degraded"}
            ):
                blockers.append("candidato sin heartbeat saludable")
        if old is not None and await self.repo.has_active_agent_work(tenant_id, old.id):
            blockers.append("existen ejecuciones activas")
        return blockers

    async def _clone_profiles(
        self, tenant_id: str, old_agent_id: uuid.UUID, candidate_id: uuid.UUID
    ) -> tuple[
        dict[str, str], list[dict[str, str]], list[AgentConnectionProfile]
    ]:
        profile_map: dict[str, str] = {}
        requiring_secret: list[dict[str, str]] = []
        ready_profiles: list[AgentConnectionProfile] = []
        for old in await self.repo.list_agent_profiles(tenant_id, old_agent_id):
            new_id = uuid.uuid4()
            destination_type = str(old.public_config.get("type") or "").lower()
            needs_secret = bool(old.secret_envelope) or (
                old.profile_type == "destination" and destination_type == "sftp"
            )
            clone = AgentConnectionProfile(
                id=new_id,
                tenant_id=old.tenant_id,
                agent_id=candidate_id,
                profile_type=old.profile_type,
                profile_key=old.profile_key,
                label=old.label,
                public_config=dict(old.public_config),
                secret_envelope=None,
                desired_revision=old.desired_revision + 1,
                applied_revision=0,
                sync_status="requires_secret" if needs_secret else "pending",
                last_error=(
                    "Capture y pruebe la credencial en el servidor nuevo"
                    if needs_secret
                    else None
                ),
                is_active=old.is_active,
            )
            self.db.add(clone)
            profile_map[str(old.id)] = str(new_id)
            if needs_secret:
                requiring_secret.append(
                    {
                        "profileId": str(new_id),
                        "profileType": old.profile_type,
                        "label": old.label,
                    }
                )
            else:
                ready_profiles.append(clone)
        return profile_map, requiring_secret, ready_profiles

    async def _serialize(
        self,
        tenant_id: str,
        session: AgentReplacementSession,
        *,
        old=None,
        candidate=None,
    ) -> dict[str, Any]:
        old = old or await self.repo.get_agent(tenant_id, str(session.old_agent_id))
        candidate = candidate or (
            await self.repo.get_agent(tenant_id, str(session.candidate_agent_id))
            if session.candidate_agent_id
            else None
        )
        blockers = (
            await self._blockers(tenant_id, session, old, candidate)
            if session.status == "awaiting_confirmation"
            else []
        )
        old_profiles = await self.repo.list_agent_profiles(tenant_id, old.id)
        requiring_secret = [
            {
                "profileId": str(item.id),
                "profileType": item.profile_type,
                "label": item.label,
            }
            for item in old_profiles
            if item.secret_envelope
            or (
                item.profile_type == "destination"
                and str(item.public_config.get("type") or "").lower() == "sftp"
            )
        ]
        if session.status == "completed":
            requiring_secret = list(
                (session.audit_json or {}).get("profilesRequiringSecret")
                or requiring_secret
            )
        return {
            "id": str(session.id),
            "status": session.status,
            "expiresAt": session.expires_at.isoformat(),
            "oldAgent": await self._machine(tenant_id, old),
            "candidateAgent": (
                await self._machine(tenant_id, candidate) if candidate else None
            ),
            "profilesRequiringSecret": requiring_secret,
            "canConfirm": session.status == "awaiting_confirmation" and not blockers,
            "blockers": blockers,
            "code": None,
        }

    async def _machine(self, tenant_id: str, agent) -> dict[str, Any]:
        volumes = await self.repo.list_agent_volumes(tenant_id, agent.id)
        return {
            "id": str(agent.id),
            "hostname": agent.hostname,
            "agentVersion": agent.agent_version,
            "status": agent.status,
            "healthStatus": agent.health_status,
            "lastHeartbeatAt": (
                agent.last_heartbeat_at.isoformat() if agent.last_heartbeat_at else None
            ),
            "volumes": [
                {
                    "volumeKey": item.volume_key,
                    "label": item.label,
                    "mountPoint": item.mount_point,
                    "totalBytes": item.total_bytes,
                    "freeBytes": item.free_bytes,
                }
                for item in volumes
            ],
            "sqlCandidates": list((agent.metadata_json or {}).get("sqlInstances") or []),
        }
