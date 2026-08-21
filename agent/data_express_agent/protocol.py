"""Contrato criptográfico v1 compartido con el backend de Railway."""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


REQUEST_CONTEXT = b"DATAEXPRESS-AGENT-REQUEST-V1"
COMMAND_CONTEXT = b"DATAEXPRESS-AGENT-COMMAND-V1"
DEFAULT_MAX_CLOCK_SKEW_SECONDS = 120
FILE_BACKUP_CAPABILITY = "file_backup_v1"
MANAGED_FILE_COMMAND_TYPES = frozenset(
    {
        "apply_file_backup_config",
        "simulate_file_backup",
        "run_file_backup",
        "resume_file_backup",
        "cancel_file_backup",
        "simulate_file_restore",
        "run_file_restore",
        "test_file_destination",
    }
)


class AgentProtocolError(ValueError):
    def __init__(self, code: str, message: str = "Autenticación del agente inválida"):
        super().__init__(message)
        self.code = code


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str, *, error_code: str) -> bytes:
    try:
        if not value or not value.isascii():
            raise ValueError
        padded = value + "=" * (-len(value) % 4)
        return base64.b64decode(
            padded.encode("ascii"), altchars=b"-_", validate=True
        )
    except (ValueError, binascii.Error, UnicodeError) as exc:
        raise AgentProtocolError(error_code) from exc


def _body_hash(body: bytes) -> str:
    if not isinstance(body, bytes):
        raise AgentProtocolError("AGENT_BODY_INVALID")
    return hashlib.sha256(body).hexdigest()


def request_signing_message(
    *,
    method: str,
    path_with_query: str,
    timestamp: int,
    nonce: str,
    body: bytes,
) -> bytes:
    normalized_method = method.strip().upper()
    if not normalized_method or "\n" in normalized_method:
        raise AgentProtocolError("AGENT_REQUEST_INVALID")
    if not path_with_query.startswith("/") or "\n" in path_with_query:
        raise AgentProtocolError("AGENT_REQUEST_INVALID")
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        raise AgentProtocolError("AGENT_TIMESTAMP_INVALID")
    if not nonce or len(nonce) > 128 or "\n" in nonce:
        raise AgentProtocolError("AGENT_NONCE_INVALID")
    return b"\n".join(
        (
            REQUEST_CONTEXT,
            normalized_method.encode("ascii"),
            path_with_query.encode("utf-8"),
            str(timestamp).encode("ascii"),
            nonce.encode("ascii"),
            _body_hash(body).encode("ascii"),
        )
    )


def sign_request(
    private_key: Ed25519PrivateKey,
    *,
    method: str,
    path_with_query: str,
    timestamp: int,
    nonce: str,
    body: bytes,
) -> str:
    return _base64url_encode(
        private_key.sign(
            request_signing_message(
                method=method,
                path_with_query=path_with_query,
                timestamp=timestamp,
                nonce=nonce,
                body=body,
            )
        )
    )


def verify_request(
    public_key: Ed25519PublicKey,
    *,
    signature: str,
    method: str,
    path_with_query: str,
    timestamp: int,
    nonce: str,
    body: bytes,
    now: int,
    max_clock_skew: int = DEFAULT_MAX_CLOCK_SKEW_SECONDS,
    nonce_available: Callable[[str], bool] | None = None,
) -> None:
    if (
        not isinstance(now, int)
        or isinstance(now, bool)
        or max_clock_skew < 0
        or abs(now - timestamp) > max_clock_skew
    ):
        raise AgentProtocolError("AGENT_TIMESTAMP_INVALID")
    message = request_signing_message(
        method=method,
        path_with_query=path_with_query,
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    raw_signature = _base64url_decode(
        signature, error_code="AGENT_SIGNATURE_INVALID"
    )
    try:
        public_key.verify(raw_signature, message)
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise AgentProtocolError("AGENT_SIGNATURE_INVALID") from exc
    if nonce_available is not None and not nonce_available(nonce):
        raise AgentProtocolError("AGENT_REPLAY_DETECTED")


def command_signing_message(key_id: str, body: bytes) -> bytes:
    if not key_id or len(key_id) > 100 or "\n" in key_id:
        raise AgentProtocolError("AGENT_KEY_ID_INVALID")
    return b"\n".join(
        (COMMAND_CONTEXT, key_id.encode("ascii"), _body_hash(body).encode("ascii"))
    )


def sign_command(
    private_key: Ed25519PrivateKey, key_id: str, body: bytes
) -> str:
    return _base64url_encode(
        private_key.sign(command_signing_message(key_id, body))
    )


def verify_command(
    public_key: Ed25519PublicKey,
    key_id: str,
    body: bytes,
    signature: str,
) -> None:
    raw_signature = _base64url_decode(
        signature, error_code="AGENT_SIGNATURE_INVALID"
    )
    try:
        public_key.verify(raw_signature, command_signing_message(key_id, body))
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise AgentProtocolError("AGENT_SIGNATURE_INVALID") from exc


def private_key_to_base64(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return _base64url_encode(raw)


def public_key_to_base64(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _base64url_encode(raw)


def load_private_key(value: str) -> Ed25519PrivateKey:
    try:
        if value.strip().startswith("-----BEGIN"):
            key = serialization.load_pem_private_key(value.encode("ascii"), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError
            return key
        raw = _base64url_decode(value.strip(), error_code="AGENT_KEY_INVALID")
        if len(raw) != 32:
            raise ValueError
        return Ed25519PrivateKey.from_private_bytes(raw)
    except AgentProtocolError:
        raise
    except (ValueError, TypeError, UnicodeError) as exc:
        raise AgentProtocolError("AGENT_KEY_INVALID") from exc


def load_public_key(value: str) -> Ed25519PublicKey:
    try:
        if value.strip().startswith("-----BEGIN"):
            key = serialization.load_pem_public_key(value.encode("ascii"))
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError
            return key
        raw = _base64url_decode(value.strip(), error_code="AGENT_KEY_INVALID")
        if len(raw) != 32:
            raise ValueError
        return Ed25519PublicKey.from_public_bytes(raw)
    except AgentProtocolError:
        raise
    except (ValueError, TypeError, UnicodeError) as exc:
        raise AgentProtocolError("AGENT_KEY_INVALID") from exc

