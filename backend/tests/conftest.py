"""
Configuración de las pruebas de humo. Prepara un entorno aislado ANTES de importar
`dev_server` (que lee SECRET_KEY y DB_PATH al importarse): SECRET_KEY válida de test
y una base de datos SQLite temporal, para no tocar datos reales.
"""
import os
import sys
import tempfile
from pathlib import Path

# backend/ en sys.path para importar dev_server y persistence
_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

# Debe fijarse ANTES de importar dev_server
os.environ.setdefault("SECRET_KEY", "test-secret-" + "a" * 52)   # válida (no débil)
os.environ["DB_PATH"] = str(Path(tempfile.gettempdir()) / "infra_platform_pytest.db")

# BD limpia al inicio de la sesión de pruebas
for _suffix in ("", "-wal", "-shm"):
    _p = Path(os.environ["DB_PATH"] + _suffix)
    if _p.exists():
        _p.unlink()

import pytest
from fastapi.testclient import TestClient
import dev_server


@pytest.fixture(scope="session")
def app():
    return dev_server.app


@pytest.fixture()
def client(app):
    """Cliente HTTP con jar de cookies propio por test."""
    return TestClient(app)


@pytest.fixture()
def admin_client(client):
    """Cliente ya autenticado como admin (cookies de sesión fijadas)."""
    r = client.post(
        "/api/v1/auth/login",
        data={"username": "admin@primee.local", "password": "Admin1234!"},
    )
    assert r.status_code == 200, r.text
    return client
