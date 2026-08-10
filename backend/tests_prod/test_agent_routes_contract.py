from app.main import app


def test_admin_and_agent_routes_are_versioned_and_separated():
    paths = {route.path for route in app.routes}

    assert "/api/v1/agents" in paths
    assert "/api/v1/agents/pairing-codes" in paths
    assert "/api/v1/agents/{agent_id}/replace" in paths
    assert "/api/v1/agents/{agent_id}/revoke" in paths
    assert "/agent/v1/enroll" in paths

