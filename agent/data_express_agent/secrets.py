from __future__ import annotations

import base64
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


ENVELOPE_INFO = b"DATAEXPRESS-AGENT-SECRET-V1"


class SecretEnvelopeError(ValueError):
    pass


def _decode(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeError) as exc:
        raise SecretEnvelopeError("El sobre cifrado no es válido") from exc


def open_secret_envelope(
    private_key: X25519PrivateKey,
    envelope: str,
    *,
    context: bytes,
) -> dict:
    try:
        document = json.loads(envelope)
        if document.get("version") != 1:
            raise ValueError
        ephemeral_raw = _decode(document["ephemeralPublicKey"])
        nonce = _decode(document["nonce"])
        ciphertext = _decode(document["ciphertext"])
        if len(ephemeral_raw) != 32 or len(nonce) != 12:
            raise ValueError
        shared = private_key.exchange(X25519PublicKey.from_public_bytes(ephemeral_raw))
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=ENVELOPE_INFO + context,
        ).derive(shared)
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, context)
        value = json.loads(plaintext)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (InvalidTag, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, SecretEnvelopeError):
            raise
        raise SecretEnvelopeError("El sobre cifrado no es válido") from exc


def seal_secret_envelope(
    public_key: X25519PublicKey,
    value: dict,
    *,
    context: bytes,
) -> str:
    ephemeral = X25519PrivateKey.generate()
    shared = ephemeral.exchange(public_key)
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=ENVELOPE_INFO + context,
    ).derive(shared)
    nonce = os.urandom(12)
    plaintext = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, context)
    ephemeral_public = ephemeral.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return json.dumps(
        {
            "version": 1,
            "ephemeralPublicKey": base64.b64encode(ephemeral_public).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        },
        separators=(",", ":"),
    )
