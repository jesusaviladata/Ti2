from app.main import app


def test_agent_replacement_routes_require_explicit_compare_confirm_flow():
    routes = {(route.path, method) for route in app.routes for method in route.methods}

    assert ("/api/v1/agents/{agent_id}/replacement-sessions", "POST") in routes
    assert ("/api/v1/agents/replacement-sessions/{session_id}", "GET") in routes
    assert (
        "/api/v1/agents/replacement-sessions/{session_id}/confirm",
        "POST",
    ) in routes
    assert (
        "/api/v1/agents/replacement-sessions/{session_id}/cancel",
        "POST",
    ) in routes
    assert ("/api/v1/agents/{agent_id}/replace", "POST") in routes


def test_replacement_creation_and_confirmation_use_configuration_capability():
    routes = {route.path: route for route in app.routes}
    create = routes["/api/v1/agents/{agent_id}/replacement-sessions"]
    confirm = routes[
        "/api/v1/agents/replacement-sessions/{session_id}/confirm"
    ]

    assert create.dependant.dependencies
    assert confirm.dependant.dependencies
