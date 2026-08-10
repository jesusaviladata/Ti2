from starlette.requests import Request

from app.core.security import create_access_token
from app.middleware.audit import _extract_identity


def _request(*, cookie: str = "", authorization: str = "") -> Request:
    headers = []
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    if authorization:
        headers.append((b"authorization", authorization.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/access/sessions",
            "headers": headers,
        }
    )


def test_audit_identity_supports_normal_cookie_sessions():
    user_id = "b9e63d65-cea7-4e7a-93b5-a73482e75dc5"
    tenant_id = "19b152b0-91cc-4cf9-ac87-710d50fde3ef"
    token = create_access_token(user_id, tenant_id=tenant_id, sid="session")
    assert _extract_identity(_request(cookie=f"access_token={token}")) == (
        user_id,
        tenant_id,
    )


def test_audit_identity_supports_bearer_sessions():
    user_id = "0664ca37-2ee9-48cc-a916-5fb49bd32d72"
    tenant_id = "34b1aed9-e57d-4745-9496-540b4526e042"
    token = create_access_token(user_id, tenant_id=tenant_id, sid="session")
    assert _extract_identity(
        _request(authorization=f"Bearer {token}")
    ) == (user_id, tenant_id)
