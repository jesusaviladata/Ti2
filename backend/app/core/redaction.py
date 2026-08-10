from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "password",
    "passphrase",
    "privatekey",
    "private_key",
    "secret",
    "secret_key",
    "token",
    "access_token",
    "refresh_token",
    "connection_string",
    "database_url",
}


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "***" if str(key).lower() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item) for item in value]
    return value
