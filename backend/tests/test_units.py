"""
Pruebas unitarias de la lógica pura extraída del monolito (C-11):
sql_helpers y cleanup_rules.
"""
from sql_helpers import ENCRYPT_MAP, safe_error, stripe_paths
from cleanup_rules import apply_keep_policy


# ── sql_helpers.safe_error ──────────────────────────────────────────────────────
def test_safe_error_redacts_credentials():
    msg = safe_error(Exception("login failed UID=sa;PWD=secreto;SERVER=x"))
    assert "secreto" not in msg
    assert "PWD=***" in msg
    assert "UID=***" in msg
    assert "SERVER=x" in msg  # lo no sensible se conserva


def test_safe_error_truncates():
    assert len(safe_error(Exception("x" * 1000))) <= 512


# ── sql_helpers.stripe_paths ────────────────────────────────────────────────────
def test_stripe_paths_single():
    assert stripe_paths(r"C:\bak\db.bak", 1) == [r"C:\bak\db.bak"]
    assert stripe_paths(r"C:\bak\db.bak", 0) == [r"C:\bak\db.bak"]


def test_stripe_paths_multiple():
    paths = stripe_paths(r"C:\bak\db.bak", 3)
    assert len(paths) == 3
    assert all("part" in p and p.endswith(".bak") for p in paths)
    assert "1of3" in paths[0] and "3of3" in paths[2]


def test_encrypt_map():
    assert ENCRYPT_MAP["mandatory"] == "yes"
    assert ENCRYPT_MAP["optional"] == "no"
    assert ENCRYPT_MAP["strict"] == "strict"


# ── cleanup_rules.apply_keep_policy ─────────────────────────────────────────────
def _files(*ages_dates):
    """Helper: crea archivos {ageDays, modifiedAt} a partir de (age, fecha)."""
    return [{"ageDays": a, "modifiedAt": d, "name": d} for a, d in ages_dates]


def test_keep_all_deletes_nothing():
    files = _files((10, "2026-01-01"), (5, "2026-02-01"))
    assert apply_keep_policy(files, {"keep": "all"}) == []


def test_keep_latest_deletes_all_but_newest():
    files = _files((10, "2026-01-01"), (5, "2026-03-01"), (7, "2026-02-01"))
    eligible = apply_keep_policy(files, {"keep": "latest"})
    names = {f["modifiedAt"] for f in eligible}
    assert names == {"2026-01-01", "2026-02-01"}  # se conserva el más nuevo (03-01)


def test_keep_latest_single_file():
    files = _files((10, "2026-01-01"))
    assert apply_keep_policy(files, {"keep": "latest"}) == []


def test_keep_latest_n():
    files = _files((9, "2026-01-01"), (8, "2026-02-01"), (7, "2026-03-01"), (6, "2026-04-01"))
    eligible = apply_keep_policy(files, {"keep": "latest_n", "keepN": 2})
    kept = {f["modifiedAt"] for f in _files((9, "2026-01-01"), (8, "2026-02-01"))}
    assert {f["modifiedAt"] for f in eligible} == kept  # borra los 2 más viejos


def test_keep_none_deletes_all():
    files = _files((10, "2026-01-01"), (5, "2026-02-01"))
    assert len(apply_keep_policy(files, {"keep": "none"})) == 2


def test_min_age_filters():
    files = _files((1, "2026-01-01"), (30, "2026-02-01"))
    # solo el de 30 días supera minAgeDays=7; con 1 candidato y keep=latest → nada
    eligible = apply_keep_policy(files, {"keep": "latest", "minAgeDays": 7})
    assert eligible == []
