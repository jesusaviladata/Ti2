"""
Pruebas de configuración de seguridad que requieren un proceso aislado:
- SECRET_KEY débil/por defecto aborta el arranque (C-6).
- La persistencia guarda en SQLite (C-7).
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent


def test_weak_secret_key_aborts():
    """Arrancar con SECRET_KEY por defecto debe fallar (fail-fast, C-6)."""
    env = dict(os.environ, SECRET_KEY="CHANGE_ME", PYTHONPATH=str(_BACKEND))
    r = subprocess.run(
        [sys.executable, "-c", "import dev_server"],
        capture_output=True, text=True, env=env, cwd=str(_BACKEND),
    )
    assert r.returncode != 0, "el arranque debería abortar con SECRET_KEY débil"
    assert "SECRET_KEY" in (r.stdout + r.stderr)


def test_persistence_saves_to_sqlite():
    """persistence.save() escribe los documentos en la BD SQLite (C-7)."""
    import persistence

    bucket = {"k1": {"id": "k1", "x": 42}}
    persistence.register("pytest_bucket", bucket)
    persistence.init()
    persistence.save()

    cn = sqlite3.connect(persistence.DB_PATH)
    try:
        row = cn.execute('SELECT data FROM pytest_bucket WHERE id = ?', ("k1",)).fetchone()
    finally:
        cn.close()

    assert row is not None, "el documento no se persistió"
    assert json.loads(row[0])["x"] == 42
