from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.agent_protocol import AgentProtocolError, load_public_key, verify_request
from app.core.errors import DomainError
from app.models.operations import RemoteAgent
from app.repositories.agent_repository import AgentRepository


class AgentAuthService:
    """Authenticate agent requests without disclosing the failed check."""

    def __init__(
        self,
        db: Any | None = None,
        *,
        repo: AgentRepository | Any | None = None,
        now: Callable[[], int] | None = None,
        max_clock_skew: int = 120,
    ):
        if repo is None and db is None:
            raise ValueError("db or repo is required")
        self.repo = repo or AgentRepository(db)
        self.now = now or (lambda: int(time.time()))
        self.max_clock_skew = max_clock_skew

    @staticmethod
    def _invalid() -> DomainError:
        return DomainError(
            "AGENT_AUTH_INVALID",
            "No fue posible autenticar el agente",
            401,
        )

    async def authenticate(
        self,
        *,
        agent_id: str,
        timestamp: str,
        nonce: str,
        signature: str,
        method: str,
        path_with_query: str,
        body: bytes,
    ) -> RemoteAgent:
        try:
            parsed_timestamp = int(timestamp)
            if str(parsed_timestamp) != timestamp.strip():
                raise ValueError
            agent = await self.repo.get_agent_unscoped(agent_id)
            if agent is None or agent.status == "revoked" or agent.revoked_at is not None:
                raise AgentProtocolError("AGENT_IDENTITY_INVALID")
            verify_request(
                load_public_key(agent.public_key),
                signature=signature,
                method=method,
                path_with_query=path_with_query,
                timestamp=parsed_timestamp,
                nonce=nonce,
                body=body,
                now=self.now(),
                max_clock_skew=self.max_clock_skew,
            )
            nonce_hash = hashlib.sha256(nonce.encode("ascii")).hexdigest()
            expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=self.max_clock_skew * 2
            )
            if not await self.repo.reserve_nonce(agent, nonce_hash, expires_at):
                raise AgentProtocolError("AGENT_REPLAY_DETECTED")
        except (AgentProtocolError, ValueError, TypeError, UnicodeError, OverflowError):
            raise self._invalid() from None

        agent.last_seen_at = datetime.now(timezone.utc)
        agent.status = "connected"
        await self.repo.flush()
        return agent

