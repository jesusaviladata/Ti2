from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0010_agent_storage_preference.py"
)


def test_storage_preference_migration_follows_current_head():
    text = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "0010"' in text
    assert 'down_revision: Union[str, None] = "0009"' in text
    assert '"preferred_agent_id"' in text
    assert '"preferred_volume_key"' in text
    assert 'ondelete="SET NULL"' in text
