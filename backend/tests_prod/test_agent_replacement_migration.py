from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "0012_agent_replacement_sessions.py"


def test_replacement_migration_follows_file_backup_head_and_adds_two_phase_state():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "0012"' in source
    assert 'down_revision: Union[str, None] = "0011"' in source
    assert '"agent_replacement_sessions"' in source
    assert '"replacement_session_id"' in source
    assert '"lineage_id"' in source
    assert "UPDATE remote_agents SET lineage_id = id" in source


def test_replacement_migration_never_persists_plain_pairing_codes():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'sa.Column("code"' not in source
    assert 'sa.Column("pairing_code"' not in source
