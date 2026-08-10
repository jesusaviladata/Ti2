from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agent.data_express_agent import protocol


def test_agent_rejects_command_signed_for_another_key_id():
    private_key = Ed25519PrivateKey.generate()
    body = b'{"type":"validate_structure"}'
    signature = protocol.sign_command(private_key, "key-current", body)

    with pytest.raises(protocol.AgentProtocolError) as error:
        protocol.verify_command(
            private_key.public_key(),
            "key-next",
            body,
            signature,
        )

    assert error.value.code == "AGENT_SIGNATURE_INVALID"


def test_agent_rejects_malformed_signature_without_leaking_details():
    private_key = Ed25519PrivateKey.generate()

    with pytest.raises(protocol.AgentProtocolError) as error:
        protocol.verify_command(
            private_key.public_key(),
            "key-current",
            b"payload",
            "%%%",
        )

    assert error.value.code == "AGENT_SIGNATURE_INVALID"
    assert "signature" not in str(error.value).lower()

