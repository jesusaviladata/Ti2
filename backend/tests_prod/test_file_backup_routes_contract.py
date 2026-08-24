from app.api.v1 import file_backups
from app.main import app


def test_file_backup_router_registers_approved_resource_routes():
    routes = {
        (method, route.path)
        for route in file_backups.router.routes
        for method in route.methods
    }
    expected = {
        ("GET", "/tasks"),
        ("POST", "/tasks"),
        ("GET", "/tasks/{task_id}"),
        ("PATCH", "/tasks/{task_id}"),
        ("DELETE", "/tasks/{task_id}"),
        ("POST", "/tasks/{task_id}/simulations"),
        ("GET", "/simulations/{simulation_id}"),
        ("GET", "/tasks/{task_id}/runs"),
        ("POST", "/tasks/{task_id}/runs"),
        ("GET", "/runs/{run_id}"),
        ("POST", "/runs/{run_id}/cancellations"),
        ("POST", "/restores"),
        ("GET", "/restores/{restore_id}"),
        ("POST", "/restores/{restore_id}/confirmations"),
        ("GET", "/chains/{chain_id}"),
        ("PATCH", "/artifacts/{artifact_id}"),
    }

    assert expected <= routes


def test_production_app_mounts_file_backup_router():
    paths = {route.path for route in app.routes}

    assert "/api/v1/file-backup/tasks" in paths
    assert "/api/v1/file-backup/restores" in paths
    assert "/api/v1/file-backup/artifacts/{artifact_id}" in paths


def test_file_backup_endpoints_never_use_not_implemented_status():
    for route in file_backups.router.routes:
        endpoint = route.endpoint
        assert 501 not in endpoint.__code__.co_consts, route.path
