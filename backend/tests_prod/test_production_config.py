import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_rejects_short_or_placeholder_secret():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="short")

    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="CHANGE_ME_generate_with_openssl_rand_hex_32")


def test_production_requires_https_and_secure_cookies():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            APP_ENV="production",
            APP_ORIGIN="http://dataexpress.example",
            COOKIE_SECURE=False,
            SECRET_KEY="s" * 64,
        )


def test_secure_production_configuration_is_accepted():
    configured = Settings(
        _env_file=None,
        APP_ENV="production",
        APP_ORIGIN="https://dataexpress.example",
        COOKIE_SECURE=True,
        SECRET_KEY="s" * 64,
    )

    assert configured.COOKIE_SECURE is True
