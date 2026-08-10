import pytest

from app.core.errors import DomainError
from app.services.remote_transport import validate_remote_path


def test_remote_paths_must_be_absolute():
    with pytest.raises(DomainError) as error:
        validate_remote_path("relative/path", ["relative/path"])
    assert error.value.code == "REMOTE_PATH_NOT_ABSOLUTE"


def test_remote_paths_inside_absolute_allowlist_are_accepted():
    assert validate_remote_path("/data/client-a/logs", ["/data/client-a"]) == (
        "/data/client-a/logs"
    )
