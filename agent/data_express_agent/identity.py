from __future__ import annotations

import base64
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .dpapi import SecretProtector, WindowsDpapiProtector
from .protocol import (
    load_private_key,
    private_key_to_base64,
    public_key_to_base64,
)


class AgentIdentityError(RuntimeError):
    pass


@dataclass(slots=True)
class AgentIdentity:
    installation_id: str
    private_key: Ed25519PrivateKey
    agent_id: str | None = None
    tenant_id: str | None = None

    @classmethod
    def generate(cls) -> "AgentIdentity":
        return cls(str(uuid.uuid4()), Ed25519PrivateKey.generate())

    @property
    def public_key(self) -> str:
        return public_key_to_base64(self.private_key.public_key())

    @property
    def enrolled(self) -> bool:
        return bool(self.agent_id and self.tenant_id)


class IdentityStore:
    def __init__(self, path: Path, protector: SecretProtector | None = None):
        self.path = path
        self.protector = protector or WindowsDpapiProtector()

    def save(self, identity: AgentIdentity) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        private_bytes = private_key_to_base64(identity.private_key).encode("ascii")
        protected = self.protector.protect(private_bytes)
        document = {
            "version": 1,
            "installationId": identity.installation_id,
            "agentId": identity.agent_id,
            "tenantId": identity.tenant_id,
            "protectedPrivateKey": base64.b64encode(protected).decode("ascii"),
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(document, separators=(",", ":")), encoding="utf-8"
        )
        os.replace(temporary, self.path)

    def load(self) -> AgentIdentity:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if document.get("version") != 1:
                raise ValueError
            protected = base64.b64decode(
                document["protectedPrivateKey"].encode("ascii"), validate=True
            )
            private_key = load_private_key(
                self.protector.unprotect(protected).decode("ascii")
            )
            installation_id = str(uuid.UUID(document["installationId"]))
            agent_id = document.get("agentId")
            tenant_id = document.get("tenantId")
            if agent_id:
                agent_id = str(uuid.UUID(agent_id))
            if tenant_id:
                tenant_id = str(uuid.UUID(tenant_id))
            return AgentIdentity(
                installation_id=installation_id,
                private_key=private_key,
                agent_id=agent_id,
                tenant_id=tenant_id,
            )
        except Exception as exc:
            raise AgentIdentityError("No se pudo abrir la identidad protegida") from exc

    def load_or_create(self) -> AgentIdentity:
        if self.path.exists():
            return self.load()
        identity = AgentIdentity.generate()
        self.save(identity)
        return identity

