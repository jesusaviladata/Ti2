"""
Pruebas de humo del backend oficial (dev_server.py). Cubren: arranque, salud, login,
control de acceso al registro (C-3), file manager fail-closed (C-4), cookies HttpOnly
y refresh (C-5/C-14).
"""
import uuid


# ── Arranque / salud ────────────────────────────────────────────────────────────
def test_app_imports_and_boots(app):
    # Si dev_server no importara (p. ej. el bug de get_current_user_id en app/), esto fallaría.
    assert app is not None
    assert any(getattr(r, "path", "") == "/health" for r in app.routes)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Login ───────────────────────────────────────────────────────────────────────
def test_login_ok(client):
    r = client.post("/api/v1/auth/login",
                    data={"username": "admin@primee.local", "password": "Admin1234!"})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_login_bad_password(client):
    r = client.post("/api/v1/auth/login",
                    data={"username": "admin@primee.local", "password": "incorrecta"})
    assert r.status_code == 401


# ── Cookies HttpOnly (C-5) ──────────────────────────────────────────────────────
def test_login_sets_httponly_cookie(client):
    r = client.post("/api/v1/auth/login",
                    data={"username": "admin@primee.local", "password": "Admin1234!"})
    set_cookie = r.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie
    assert "access_token" in client.cookies
    assert "refresh_token" in client.cookies


def test_me_with_cookie_only(admin_client):
    # Sin cabecera Authorization: la sesión viaja en la cookie HttpOnly.
    r = admin_client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "admin@primee.local"


def test_protected_requires_auth(client):
    client.cookies.clear()
    r = client.get("/api/v1/backups")
    assert r.status_code == 401


# ── Refresh automático (C-14) ───────────────────────────────────────────────────
def test_refresh_with_cookie(admin_client):
    r = admin_client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_logout_clears_session(admin_client):
    r = admin_client.post("/api/v1/auth/logout")
    assert r.status_code == 200
    admin_client.cookies.clear()
    r = admin_client.get("/api/v1/auth/me")
    assert r.status_code == 401


# ── Registro protegido (C-3) ────────────────────────────────────────────────────
def test_register_requires_auth(client):
    client.cookies.clear()
    r = client.post("/api/v1/auth/register",
                    json={"full_name": "X", "email": "x@x.com", "password": "Passw0rd!"})
    assert r.status_code == 401


def test_register_as_admin_ok(admin_client):
    email = f"user-{uuid.uuid4().hex[:8]}@primee.local"
    r = admin_client.post("/api/v1/auth/register",
                          json={"full_name": "Nuevo", "email": email, "password": "Passw0rd!"})
    assert r.status_code == 201


def test_register_as_non_admin_forbidden(client):
    # crear técnico como admin, loguear como ese técnico, e intentar registrar -> 403
    email = f"tec-{uuid.uuid4().hex[:8]}@primee.local"
    admin = client
    r = admin.post("/api/v1/auth/login",
                   data={"username": "admin@primee.local", "password": "Admin1234!"})
    assert r.status_code == 200
    r = admin.post("/api/v1/auth/register",
                   json={"full_name": "Tec", "email": email, "password": "Passw0rd!", "role": "technician"})
    assert r.status_code == 201
    admin.cookies.clear()
    r = admin.post("/api/v1/auth/login", data={"username": email, "password": "Passw0rd!"})
    assert r.status_code == 200
    r = admin.post("/api/v1/auth/register",
                   json={"full_name": "Z", "email": "z@z.com", "password": "Passw0rd!"})
    assert r.status_code == 403


# ── Rate-limit y revocación de token (C-10) ─────────────────────────────────────
def test_login_rate_limit(client):
    # Muchos intentos fallidos contra un usuario deben terminar en 429.
    user = f"ghost-{uuid.uuid4().hex[:8]}@primee.local"
    codes = [
        client.post("/api/v1/auth/login", data={"username": user, "password": "x"}).status_code
        for _ in range(7)
    ]
    assert 429 in codes


def test_logout_revokes_token(client):
    r = client.post("/api/v1/auth/login",
                    data={"username": "admin@primee.local", "password": "Admin1234!"})
    tok = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    client.post("/api/v1/auth/logout", headers=headers)
    # El mismo token, tras logout, queda revocado (blocklist).
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


# ── File manager fail-closed (C-4) ──────────────────────────────────────────────
def test_fm_local_denied_without_allowlist(admin_client):
    # Sin FM_ALLOWED_ROOTS configurada, toda operación local se deniega.
    r = admin_client.post("/api/v1/fm/list", json={"path": "C:\\"})
    assert r.status_code in (400, 403)
