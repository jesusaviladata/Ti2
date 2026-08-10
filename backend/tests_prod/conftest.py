import os
import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("SECRET_KEY", "test-secret-" + "a" * 52)


@pytest.fixture(autouse=True)
def use_memory_session_store(monkeypatch):
    from app.services import session_store
    from tests_prod.fakes import MemorySessionStore

    store = MemorySessionStore()
    monkeypatch.setattr(session_store, "_session_store", store)
    return store

