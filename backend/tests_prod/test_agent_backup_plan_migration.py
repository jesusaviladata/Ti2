from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0005_agent_backup_plans.py"


def test_agent_backup_plan_migration_is_chained_and_durable():
    text = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "0005"' in text
    assert 'down_revision: Union[str, None] = "0004"' in text
    assert '"agent_backup_plans"' in text
    assert '"database_names"' in text
    assert '"agent_id"' in text
