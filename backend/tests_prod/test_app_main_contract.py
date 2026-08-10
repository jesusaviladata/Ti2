from app.main import app
from app.models.backup import BackupType


def test_backup_log_type_matches_frontend_contract():
    assert BackupType("log") is BackupType.log


def test_production_app_mounts_all_frontend_module_prefixes():
    paths = {
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1")
    }
    expected = {
        "/api/v1/cleanup/remote/servers",
        "/api/v1/fm/list",
        "/api/v1/ssh/hostkeys",
        "/api/v1/connections/test",
        "/api/v1/access/download",
        "/api/v1/dashboard/backup-chart",
        "/api/v1/dashboard/activity",
        "/api/v1/search",
    }
    assert expected <= paths


def test_production_app_has_no_501_endpoint_implementations():
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint and endpoint.__module__.startswith("app.api.v1"):
            constants = endpoint.__code__.co_consts
            assert 501 not in constants, route.path
