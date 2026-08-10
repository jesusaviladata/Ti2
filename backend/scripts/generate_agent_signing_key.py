"""Genera material Ed25519 para firmar comandos del Windows Agent.

El valor privado se configura únicamente en Railway. El valor público se incorpora a
la configuración del instalador del agente.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.agent_protocol import private_key_to_base64, public_key_to_base64


def generate_signing_material(key_id: str) -> dict[str, str]:
    normalized = key_id.strip()
    if not (
        1 <= len(normalized) <= 64
        and all(character.isalnum() or character in "._-" for character in normalized)
    ):
        raise ValueError("key_id debe usar únicamente letras, números, punto, guion o guion bajo")
    private_key = Ed25519PrivateKey.generate()
    return {
        "keyId": normalized,
        "privateKey": private_key_to_base64(private_key),
        "publicKey": public_key_to_base64(private_key.public_key()),
    }


def main() -> None:
    default_key_id = f"railway-{datetime.now(timezone.utc):%Y-%m}"
    parser = argparse.ArgumentParser(
        description="Genera una clave Ed25519 para comandos de Data Express Agent"
    )
    parser.add_argument("--key-id", default=default_key_id)
    args = parser.parse_args()
    material = generate_signing_material(args.key_id)
    print(json.dumps(material, indent=2))
    print(
        "\nGuarda privateKey solo en Railway. "
        "El instalador recibe únicamente keyId y publicKey."
    )


if __name__ == "__main__":
    main()

