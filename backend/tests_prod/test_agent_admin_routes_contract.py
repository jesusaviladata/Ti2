from app.main import app


def test_agent_admin_explorer_validation_configuration_and_job_routes_exist():
    paths = {route.path for route in app.routes}
    assert "/api/v1/agents/{agent_id}/browse" in paths
    assert "/api/v1/agents/{agent_id}/validate" in paths
    assert "/api/v1/agents/{agent_id}/configuration" in paths
    assert "/api/v1/agents/{agent_id}/cleanup/direct" in paths
    assert "/api/v1/agents/jobs/{job_id}" in paths
    assert "/api/v1/agents/jobs/{job_id}/cancel" in paths

