from pathlib import Path

import pytest

from app.api.v1 import cleanup_runtime
from app.core.errors import DomainError
from app.services.cleanup_service import validate_configured_folder


def test_cleanup_runtime_registers_every_frontend_route():
    routes = {(method, route.path) for route in cleanup_runtime.router.routes for method in route.methods}
    expected = {
        ("GET", "/folders"),
        ("POST", "/folders"),
        ("DELETE", "/folders/{folder_id}"),
        ("GET", "/rules"),
        ("POST", "/rules"),
        ("PUT", "/rules/{rule_id}"),
        ("DELETE", "/rules/{rule_id}"),
        ("GET", "/scan"),
        ("POST", "/execute"),
        ("GET", "/trash"),
        ("DELETE", "/trash/{item_id}"),
        ("POST", "/restore/{item_id}"),
        ("GET", "/history"),
        ("GET", "/schedules"),
        ("POST", "/schedules"),
        ("PUT", "/schedules/{schedule_id}"),
        ("DELETE", "/schedules/{schedule_id}"),
    }
    assert expected <= routes


def test_cleanup_rejects_drive_or_filesystem_root():
    root = Path.cwd().anchor or "/"
    with pytest.raises(DomainError) as exc:
        validate_configured_folder(root)
    assert exc.value.code == "UNSAFE_FOLDER"


def test_cleanup_requires_absolute_configured_path():
    with pytest.raises(DomainError) as exc:
        validate_configured_folder("relative/path")
    assert exc.value.code == "INVALID_FOLDER"
