from app.main import app


def test_admin_and_agent_routes_are_versioned_and_separated():
    paths = {route.path for route in app.routes}

    assert "/api/v1/agents" in paths
    assert "/api/v1/agents/pairing-codes" in paths
    assert "/api/v1/agents/{agent_id}/replace" in paths
    assert "/api/v1/agents/{agent_id}/revoke" in paths
    assert "/api/v1/agent-storage" in paths
    assert "/api/v1/agent-storage/alerts" in paths
    assert "/api/v1/agent-storage/thresholds" in paths
    assert "/api/v1/agent-storage/preference" in paths
    assert "/api/v1/agents/{agent_id}/managed-profiles" in paths
    assert "/api/v1/agents/{agent_id}/managed-profiles/discover" in paths
    assert "/api/v1/agents/{agent_id}/managed-profiles/{profile_id}/test" in paths
    assert "/agent/v1/enroll" in paths
    assert "/api/v1/backups/runs" in paths
    assert "/api/v1/backups/plans" in paths
    assert "/api/v1/backups/{backup_id}/delivery/retry" in paths
    assert "/api/v1/cleanup/agent/simulations" in paths
    assert "/api/v1/cleanup/agent/executions" in paths
