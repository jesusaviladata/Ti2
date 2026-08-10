from app.core.security import hash_password, verify_password


def test_password_hashing_round_trip_is_supported_by_installed_runtime():
    password = "CorrectHorse123!"

    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrong-password", hashed) is False

