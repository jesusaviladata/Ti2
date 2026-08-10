"""
Pruebas de la Limpieza remota segura (Fase 1 + 3):
- Núcleo puro de seguridad: validación de rutas (traversal/allowlist) y simulación.
- Endpoints: fail-closed sin allowlist, bloqueo de '..' y de rutas fuera de la allowlist,
  y que la config de servidores exige rol admin.
"""
import uuid

import remote_cleanup as rc


# ── Validación de rutas ─────────────────────────────────────────────────────────
def test_contains_traversal():
    assert rc.contains_traversal("/BaseCore/../etc")
    assert rc.contains_traversal("a/b/../c")
    assert rc.contains_traversal("..\\Windows")     # backslash normalizado
    assert not rc.contains_traversal("/BaseCore/Logs")
    assert not rc.contains_traversal("/BaseCore/Logs/app.log")


def test_is_within_allowlist_fail_closed():
    # Sin raíces permitidas → SIEMPRE denegado (fail-closed).
    assert rc.is_within_allowlist("/BaseCore/Logs", []) is False


def test_is_within_allowlist():
    roots = ["/BaseCore/Logs", "/BaseCore/Respuesta"]
    assert rc.is_within_allowlist("/BaseCore/Logs", roots)              # raíz exacta
    assert rc.is_within_allowlist("/BaseCore/Logs/sub/app.log", roots)  # dentro
    assert rc.is_within_allowlist("/BaseCore/Respuesta/x", roots)
    assert not rc.is_within_allowlist("/BaseCore", roots)               # el padre no
    assert not rc.is_within_allowlist("/BaseCore/Logs2", roots)         # prefijo falso
    assert not rc.is_within_allowlist("/etc/passwd", roots)


def test_normalize_remote():
    assert rc.normalize_remote("C:\\BaseCore\\Logs") == "C:/BaseCore/Logs"
    assert rc.normalize_remote("/BaseCore/./Logs/") == "/BaseCore/Logs"
    assert rc.normalize_remote("/BaseCore/Logs/../Respuesta") == "/BaseCore/Respuesta"


# ── Simulación (select_candidates) ──────────────────────────────────────────────
NOW = 1_000_000_000.0
DAY = 86400.0


def _f(name, age_days, size=100, is_dir=False, modified=None):
    mod = modified if modified is not None else NOW - age_days * DAY
    return {"name": name, "path": f"/BaseCore/Logs/{name}", "sizeBytes": size,
            "modified": mod, "isDir": is_dir}


def test_sim_protected_extension_never_deleted():
    files = [_f("core.dll", 100), _f("app.log", 100)]
    rep = rc.select_candidates(files, {}, NOW)
    paths = {e["path"] for e in rep["elegibles"]}
    assert "/BaseCore/Logs/core.dll" not in paths       # protegida
    assert rep["protegidosCount"] >= 1


def test_sim_extension_allowlist():
    files = [_f("a.log", 100), _f("b.xml", 100), _f("c.tmp", 100)]
    rep = rc.select_candidates(files, {"extensionesPermitidas": [".log"]}, NOW)
    assert [e["name"] for e in rep["elegibles"]] == ["a.log"]


def test_sim_min_age():
    files = [_f("old.log", 40), _f("new.log", 2)]
    rep = rc.select_candidates(files, {"antiguedadMinimaDias": 30}, NOW)
    assert [e["name"] for e in rep["elegibles"]] == ["old.log"]


def test_sim_recent_modified_excluded():
    files = [_f("fresh.log", 0, modified=NOW - 3600)]  # hace 1 h
    rep = rc.select_candidates(files, {"noModificadoUltimasHoras": 24}, NOW)
    assert rep["elegiblesCount"] == 0
    assert any("modificado_reciente" in x["reason"] for x in rep["excluidos"])


def test_sim_exclusion_pattern():
    files = [_f("keep.log", 100), _f("audit.log", 100)]
    rep = rc.select_candidates(files, {"exclusiones": ["audit.*"]}, NOW)
    assert [e["name"] for e in rep["elegibles"]] == ["keep.log"]


def test_sim_dirs_excluded_by_default():
    files = [_f("subcarpeta", 100, is_dir=True), _f("a.log", 100)]
    rep = rc.select_candidates(files, {}, NOW)
    assert [e["name"] for e in rep["elegibles"]] == ["a.log"]


def test_sim_limit_files():
    files = [_f(f"{i}.log", 100 - i) for i in range(5)]
    rep = rc.select_candidates(files, {"limites": {"maxArchivosPorEjecucion": 2}}, NOW)
    assert rep["elegiblesCount"] == 2
    assert any(x["reason"] == "limite_archivos" for x in rep["excluidos"])


def test_sim_limit_bytes():
    files = [_f("a.log", 100, size=10), _f("b.log", 90, size=10), _f("c.log", 80, size=10)]
    rep = rc.select_candidates(files, {"limites": {"maxBytesPorEjecucion": 25}}, NOW)
    assert rep["espacioLiberadoBytes"] <= 25
    assert rep["elegiblesCount"] == 2


def test_sim_oldest_first():
    files = [_f("new.log", 5), _f("old.log", 50), _f("mid.log", 20)]
    rep = rc.select_candidates(files, {}, NOW)
    assert [e["name"] for e in rep["elegibles"]] == ["old.log", "mid.log", "new.log"]


# ── Endpoints ───────────────────────────────────────────────────────────────────
def _mk_server(client, allowlist):
    r = client.post("/api/v1/cleanup/remote/servers", json={
        "name": "Core Test", "protocol": "sftp", "host": "10.0.0.9",
        "port": 22, "username": "svc", "rutaBase": "/BaseCore", "allowlist": allowlist,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_server_config_requires_admin(client):
    # técnico no puede crear servidores
    email = f"tec-{uuid.uuid4().hex[:6]}@primee.local"
    client.post("/api/v1/auth/login", data={"username": "admin@primee.local", "password": "Admin1234!"})
    client.post("/api/v1/auth/register", json={"full_name": "T", "email": email, "password": "Passw0rd!", "role": "technician"})
    client.cookies.clear()
    client.post("/api/v1/auth/login", data={"username": email, "password": "Passw0rd!"})
    r = client.post("/api/v1/cleanup/remote/servers", json={"name": "x", "host": "h", "allowlist": []})
    assert r.status_code == 403


def test_list_fail_closed_without_allowlist(admin_client):
    sid = _mk_server(admin_client, allowlist=[])
    r = admin_client.post("/api/v1/cleanup/remote/list", json={"server_id": sid, "password": "x", "path": "/BaseCore/Logs"})
    assert r.status_code == 403
    assert "allowlist" in r.text.lower()


def test_list_blocks_traversal(admin_client):
    sid = _mk_server(admin_client, allowlist=["/BaseCore/Logs"])
    r = admin_client.post("/api/v1/cleanup/remote/list", json={"server_id": sid, "password": "x", "path": "/BaseCore/../etc"})
    assert r.status_code == 403


def test_simulate_blocks_target_outside_allowlist(admin_client):
    sid = _mk_server(admin_client, allowlist=["/BaseCore/Logs"])
    r = admin_client.post("/api/v1/cleanup/remote/simulate", json={
        "server_id": sid, "password": "x",
        "rule": {"rutasPermitidas": ["/etc"], "extensionesPermitidas": [".log"]},
    })
    assert r.status_code == 403


def test_simulate_fail_closed_without_allowlist(admin_client):
    sid = _mk_server(admin_client, allowlist=[])
    r = admin_client.post("/api/v1/cleanup/remote/simulate", json={"server_id": sid, "password": "x", "rule": {}})
    assert r.status_code == 403


# ── Cuarentena / ejecución (Fase 2 + 5) ─────────────────────────────────────────
def test_quarantine_path_pure():
    p = rc.quarantine_path("/BaseCore", "exec123", "/BaseCore/Logs/app.log")
    assert p.startswith("/BaseCore/.cuarentena_limpieza/exec123/")
    assert p.endswith("_app.log")


def test_execute_requires_confirmar(admin_client):
    sid = _mk_server(admin_client, allowlist=["/BaseCore/Logs"])
    r = admin_client.post("/api/v1/cleanup/remote/execute", json={
        "server_id": sid, "password": "x",
        "rule": {"rutasPermitidas": ["/BaseCore/Logs"]}, "confirmar": False,
    })
    assert r.status_code == 400


def test_execute_blocks_target_outside_allowlist(admin_client):
    sid = _mk_server(admin_client, allowlist=["/BaseCore/Logs"])
    r = admin_client.post("/api/v1/cleanup/remote/execute", json={
        "server_id": sid, "password": "x",
        "rule": {"rutasPermitidas": ["/etc"]}, "confirmar": True,
    })
    assert r.status_code == 403


def test_execute_concurrency_lock(admin_client):
    import dev_server as d
    sid = _mk_server(admin_client, allowlist=["/BaseCore/Logs"])
    d._CLEANUP_RUNNING.add(sid)   # simula una limpieza ya en curso
    try:
        r = admin_client.post("/api/v1/cleanup/remote/execute", json={
            "server_id": sid, "password": "x",
            "rule": {"rutasPermitidas": ["/BaseCore/Logs"]}, "confirmar": True,
        })
        assert r.status_code == 409
    finally:
        d._CLEANUP_RUNNING.discard(sid)


def _login_as_new_role(client, role):
    email = f"{role}-{uuid.uuid4().hex[:6]}@primee.local"
    client.post("/api/v1/auth/login", data={"username": "admin@primee.local", "password": "Admin1234!"})
    sid = _mk_server(client, allowlist=["/BaseCore/Logs"])
    client.post("/api/v1/auth/register", json={"full_name": "U", "email": email, "password": "Passw0rd!", "role": role})
    client.cookies.clear()
    client.post("/api/v1/auth/login", data={"username": email, "password": "Passw0rd!"})
    return sid


def test_execute_denied_for_client_role(client):
    sid = _login_as_new_role(client, "client")
    r = client.post("/api/v1/cleanup/remote/execute", json={
        "server_id": sid, "password": "x", "rule": {}, "confirmar": True,
    })
    assert r.status_code == 403


def test_purge_requires_admin(client):
    _login_as_new_role(client, "technician")
    r = client.post("/api/v1/cleanup/remote/quarantine/purge", json={"server_id": "x"})
    assert r.status_code == 403


def test_restore_requires_admin(client):
    _login_as_new_role(client, "technician")
    r = client.post("/api/v1/cleanup/remote/quarantine/none/restore", json={"server_id": "x"})
    assert r.status_code == 403


def test_history_and_quarantine_endpoints(admin_client):
    assert admin_client.get("/api/v1/cleanup/remote/history").status_code == 200
    assert admin_client.get("/api/v1/cleanup/remote/quarantine").status_code == 200


# ── Verificación de clave de host SSH (H-5) ─────────────────────────────────────
class _FakeKey:
    def __init__(self, b: bytes):
        self._b = b

    def asbytes(self) -> bytes:
        return self._b


def test_hostkey_tofu_pins_and_blocks_change():
    import pytest
    import dev_server as d
    d.SSH_HOSTKEYS.clear()
    pol = d._PinnedHostKeyPolicy("h:22", strict=False)
    k1 = _FakeKey(b"KEY-AAA")
    pol.missing_host_key(None, "h", k1)      # primer uso → fija, no lanza
    assert "h:22" in d.SSH_HOSTKEYS
    pol.missing_host_key(None, "h", k1)      # misma clave → ok
    with pytest.raises(Exception):           # clave cambiada → bloquea (MITM)
        pol.missing_host_key(None, "h", _FakeKey(b"KEY-BBB"))


def test_hostkey_strict_rejects_unknown():
    import pytest
    import dev_server as d
    d.SSH_HOSTKEYS.pop("new:22", None)
    pol = d._PinnedHostKeyPolicy("new:22", strict=True)
    with pytest.raises(Exception):
        pol.missing_host_key(None, "new", _FakeKey(b"X"))


def test_hostkeys_endpoints_require_admin(client):
    _login_as_new_role(client, "technician")
    assert client.get("/api/v1/ssh/hostkeys").status_code == 403
    assert client.post("/api/v1/ssh/hostkeys/forget", json={"host": "h", "port": 22}).status_code == 403


def test_hostkeys_list_admin_ok(admin_client):
    assert admin_client.get("/api/v1/ssh/hostkeys").status_code == 200
