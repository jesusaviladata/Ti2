import json

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from app.agent_protocol import seal_secret_for_agent
from agent.data_express_agent.secrets import SecretEnvelopeError, open_secret_envelope


def test_secret_envelope_only_opens_for_target_agent_and_context():
    target = X25519PrivateKey.generate()
    other = X25519PrivateKey.generate()
    import base64

    public = base64.b64encode(target.public_key().public_bytes_raw()).decode("ascii")
    envelope = seal_secret_for_agent(
        public,
        {"password": "super-secret"},
        context=b"agent-1:profile-1:revision-2",
    )

    assert open_secret_envelope(
        target, envelope, context=b"agent-1:profile-1:revision-2"
    ) == {"password": "super-secret"}
    with pytest.raises(SecretEnvelopeError):
        open_secret_envelope(
            other, envelope, context=b"agent-1:profile-1:revision-2"
        )
    with pytest.raises(SecretEnvelopeError):
        open_secret_envelope(target, envelope, context=b"different-context")


def test_ciphertext_tampering_fails_without_returning_partial_secret():
    import base64

    target = X25519PrivateKey.generate()
    public = base64.b64encode(target.public_key().public_bytes_raw()).decode("ascii")
    envelope = json.loads(
        seal_secret_for_agent(public, {"password": "secret"}, context=b"ctx")
    )
    ciphertext = bytearray(base64.b64decode(envelope["ciphertext"]))
    ciphertext[0] ^= 1
    envelope["ciphertext"] = base64.b64encode(ciphertext).decode("ascii")

    with pytest.raises(SecretEnvelopeError):
        open_secret_envelope(target, json.dumps(envelope), context=b"ctx")
