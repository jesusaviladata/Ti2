"""Estado del modulo de agentes Windows y custodia de su llave de firma.

El modulo puede gobernarse de tres formas:

* ``panel`` (por defecto): un administrador lo activa o desactiva desde
  Configuracion > Agentes. La primera activacion genera la llave Ed25519 de firma de
  comandos; la privada se guarda cifrada con una clave derivada de SECRET_KEY.
* ``server``: AGENT_MODULE_ENABLED=true lo fuerza encendido con la llave de las
  variables de entorno. El panel lo muestra pero no puede cambiarlo.
* ``locked``: AGENT_MODULE_SELF_SERVICE=false impide activarlo desde el panel.

Las rutas comprueban el estado de forma sincrona contra una copia en memoria. Esa
copia se recarga al arrancar, tras cada cambio y periodicamente, para que varios
procesos converjan aunque el cambio se haya hecho en otro.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import os
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_protocol import (
    AgentProtocolError,
    load_private_key,
    private_key_to_base64,
    public_key_to_base64,
)
from app.core.config import Settings, settings
from app.core.errors import DomainError
from app.models.agent_module import AGENT_MODULE_SETTINGS_ID, AgentModuleSetting


logger = logging.getLogger(__name__)

ManagedBy = Literal["panel", "server", "locked"]
KeyStatus = Literal["missing", "ok", "unreadable"]
KeySource = Literal["environment", "database"]

_WRAPPING_INFO = b"data-express/agent-command-signing-key/v1"
_ENVELOPE_PREFIX = "v1."
_NONCE_BYTES = 12


@dataclass(frozen=True)
class AgentModuleState:
    enabled: bool
    managed_by: ManagedBy
    key_status: KeyStatus
    key_source: KeySource | None = None
    key_id: str | None = None
    public_key: str | None = None
    private_key: Ed25519PrivateKey | None = field(default=None, repr=False, compare=False)


# --------------------------------------------------------------------------- llave


def _wrapping_key(secret: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=_WRAPPING_INFO
    ).derive(secret.encode("utf-8"))


def encrypt_private_key(private_key: Ed25519PrivateKey, key_id: str, secret: str) -> str:
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(_wrapping_key(secret)).encrypt(
        nonce, private_key_to_base64(private_key).encode("ascii"), key_id.encode("ascii")
    )
    return _ENVELOPE_PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_private_key(envelope: str, key_id: str, secret: str) -> Ed25519PrivateKey:
    if not envelope.startswith(_ENVELOPE_PREFIX):
        raise ValueError("formato de llave cifrada desconocido")
    try:
        blob = base64.urlsafe_b64decode(envelope[len(_ENVELOPE_PREFIX):].encode("ascii"))
        plaintext = AESGCM(_wrapping_key(secret)).decrypt(
            blob[:_NONCE_BYTES], blob[_NONCE_BYTES:], key_id.encode("ascii")
        )
        return load_private_key(plaintext.decode("ascii"))
    except (InvalidTag, binascii.Error, UnicodeError, AgentProtocolError) as exc:
        raise ValueError("la llave cifrada no se puede descifrar") from exc


def new_key_id(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    return f"panel-{moment:%Y%m%d}-{secrets.token_hex(3)}"


def _environment_key(config: Settings) -> tuple[str, Ed25519PrivateKey] | None:
    if not config.agent_signing_key_from_environment:
        return None
    return (
        config.AGENT_COMMAND_SIGNING_KEY_ID,
        load_private_key(config.AGENT_COMMAND_SIGNING_PRIVATE_KEY),
    )


# --------------------------------------------------------------------------- estado


def resolve_state(row: AgentModuleSetting | None, config: Settings | None = None) -> AgentModuleState:
    """Calcula el estado efectivo. Falla cerrado: sin llave usable no hay modulo."""
    config = config or settings
    env_key = _environment_key(config)

    if config.AGENT_MODULE_ENABLED and env_key is not None:
        key_id, private_key = env_key
        return AgentModuleState(
            enabled=True,
            managed_by="server",
            key_status="ok",
            key_source="environment",
            key_id=key_id,
            public_key=public_key_to_base64(private_key.public_key()),
            private_key=private_key,
        )

    if not config.AGENT_MODULE_SELF_SERVICE:
        return AgentModuleState(enabled=False, managed_by="locked", key_status="missing")

    wanted = bool(row is not None and row.enabled)

    if env_key is not None:
        key_id, private_key = env_key
        return AgentModuleState(
            enabled=wanted,
            managed_by="panel",
            key_status="ok",
            key_source="environment",
            key_id=key_id,
            public_key=public_key_to_base64(private_key.public_key()),
            private_key=private_key,
        )

    if row is None or not row.signing_private_key_encrypted or not row.signing_key_id:
        return AgentModuleState(enabled=False, managed_by="panel", key_status="missing")

    try:
        private_key = decrypt_private_key(
            row.signing_private_key_encrypted, row.signing_key_id, config.SECRET_KEY
        )
    except ValueError:
        if wanted:
            logger.error(
                "El modulo de agentes esta activado pero su llave de firma no se puede "
                "descifrar (keyId=%s). Se mantiene apagado. Causa probable: cambio de SECRET_KEY.",
                row.signing_key_id,
            )
        return AgentModuleState(
            enabled=False,
            managed_by="panel",
            key_status="unreadable",
            key_source="database",
            key_id=row.signing_key_id,
            public_key=row.signing_public_key,
        )

    return AgentModuleState(
        enabled=wanted,
        managed_by="panel",
        key_status="ok",
        key_source="database",
        key_id=row.signing_key_id,
        public_key=row.signing_public_key,
        private_key=private_key,
    )


# Antes de leer la BD ya se conoce el modo gestionado por el servidor: asi un fallo al
# cargar la fila no apaga un modulo que las variables de entorno fuerzan encendido.
_state: AgentModuleState = resolve_state(None)


def _publish(state: AgentModuleState) -> AgentModuleState:
    global _state
    _state = state
    return state


def current() -> AgentModuleState:
    return _state


def is_enabled() -> bool:
    return _state.enabled


def require_enabled() -> None:
    if not _state.enabled:
        raise DomainError(
            "AGENT_MODULE_DISABLED", "El módulo de agentes no está habilitado", 503
        )


def signing_material() -> tuple[str, Ed25519PrivateKey]:
    # Una llave de entorno manda siempre y se lee en cada firma, como antes.
    env_key = _environment_key(settings)
    if env_key is not None:
        return env_key
    state = _state
    if state.private_key is None or state.key_id is None:
        raise DomainError(
            "AGENT_SIGNING_KEY_UNAVAILABLE",
            "No hay una llave de firma disponible para los comandos del agente",
            503,
        )
    return state.key_id, state.private_key


def active_key_id() -> str:
    return signing_material()[0]


# --------------------------------------------------------------------------- BD


async def _load_row(db: AsyncSession, *, for_update: bool = False) -> AgentModuleSetting | None:
    statement = select(AgentModuleSetting).where(
        AgentModuleSetting.id == AGENT_MODULE_SETTINGS_ID
    )
    if for_update:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def reload(db: AsyncSession) -> AgentModuleState:
    return _publish(resolve_state(await _load_row(db)))


async def set_enabled(
    db: AsyncSession, *, enabled: bool, actor_id: uuid.UUID | str | None
) -> AgentModuleState:
    if settings.AGENT_MODULE_ENABLED:
        raise DomainError(
            "AGENT_MODULE_SERVER_MANAGED",
            "El módulo de agentes lo fija la configuración del servidor y no se puede cambiar desde el panel",
            409,
        )
    if not settings.AGENT_MODULE_SELF_SERVICE:
        raise DomainError(
            "AGENT_MODULE_SELF_SERVICE_DISABLED",
            "Este servidor no permite activar el módulo de agentes desde el panel",
            403,
        )

    await db.execute(
        pg_insert(AgentModuleSetting)
        .values(id=AGENT_MODULE_SETTINGS_ID, enabled=False)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    row = await _load_row(db, for_update=True)
    assert row is not None

    if enabled and not settings.agent_signing_key_from_environment:
        if not row.signing_private_key_encrypted or not row.signing_key_id:
            private_key = Ed25519PrivateKey.generate()
            key_id = new_key_id()
            row.signing_key_id = key_id
            row.signing_public_key = public_key_to_base64(private_key.public_key())
            row.signing_private_key_encrypted = encrypt_private_key(
                private_key, key_id, settings.SECRET_KEY
            )
            logger.info("Se genero la llave de firma de comandos del agente keyId=%s", key_id)
        else:
            try:
                decrypt_private_key(
                    row.signing_private_key_encrypted, row.signing_key_id, settings.SECRET_KEY
                )
            except ValueError:
                raise DomainError(
                    "AGENT_SIGNING_KEY_UNREADABLE",
                    "La llave de firma guardada no se puede descifrar. Suele ocurrir cuando "
                    "cambia SECRET_KEY.",
                    409,
                ) from None

    row.enabled = enabled
    row.updated_by = uuid.UUID(str(actor_id)) if actor_id else None
    await db.commit()

    state = _publish(resolve_state(row))
    logger.info(
        "Modulo de agentes %s desde el panel por el usuario %s",
        "activado" if state.enabled else "desactivado",
        actor_id,
    )
    return state


async def refresh_forever(session_factory: async_sessionmaker, interval_seconds: int) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with session_factory() as db:
                await reload(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("No se pudo refrescar el estado del modulo de agentes", exc_info=True)


# --------------------------------------------------------------------------- vistas


def public_view(state: AgentModuleState, *, can_manage: bool) -> dict[str, Any]:
    return {
        "enabled": state.enabled,
        "managedBy": state.managed_by,
        "canManage": bool(can_manage and state.managed_by == "panel"),
        "keyStatus": state.key_status,
        "keySource": state.key_source,
        "keyId": state.key_id,
        "publicKey": state.public_key,
        "controlPlaneUrl": settings.agent_control_plane_url,
        "packageVersion": settings.AGENT_PACKAGE_VERSION,
    }


def bootstrap_document(state: AgentModuleState) -> dict[str, Any]:
    """Mismo esquema que genera agent/package.ps1 para bootstrap.json."""
    if not state.enabled or not state.key_id or not state.public_key:
        raise DomainError(
            "AGENT_MODULE_DISABLED", "El módulo de agentes no está habilitado", 503
        )
    url = settings.agent_control_plane_url
    if urlsplit(url).scheme != "https":
        raise DomainError(
            "AGENT_CONTROL_PLANE_INSECURE",
            "El agente solo se conecta por HTTPS. Configure AGENT_CONTROL_PLANE_URL o APP_ORIGIN con https://",
            409,
        )
    return {
        "schemaVersion": 1,
        "controlPlaneUrl": url,
        "agentVersion": settings.AGENT_PACKAGE_VERSION,
        "commandTrust": {
            "activeKeyId": state.key_id,
            "keys": [{"keyId": state.key_id, "publicKey": state.public_key}],
        },
        "pollWaitSeconds": 25,
        "requestTimeoutSeconds": 40,
        "heartbeatIntervalSeconds": 30,
    }
