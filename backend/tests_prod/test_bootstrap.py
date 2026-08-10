import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "seed_admin.py"


def _module():
    spec = importlib.util.spec_from_file_location("seed_admin", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_bootstrap_requires_explicit_strong_credentials(monkeypatch):
    seed_admin = _module()
    monkeypatch.delenv("BOOTSTRAP_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    with pytest.raises(SystemExit):
        seed_admin.bootstrap_credentials()

    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "admin@dataexpress.example")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "Admin1234!")
    with pytest.raises(SystemExit):
        seed_admin.bootstrap_credentials()


def test_bootstrap_accepts_explicit_strong_credentials(monkeypatch):
    seed_admin = _module()
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "ADMIN@DataExpress.Example")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "A-unique-long-password-2026")

    email, password = seed_admin.bootstrap_credentials()

    assert email == "admin@dataexpress.example"
    assert password == "A-unique-long-password-2026"
