from pathlib import Path


VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
BASE_PLAN_MIGRATION = VERSIONS / "0005_agent_backup_plans.py"
DAY_MIGRATION = VERSIONS / "0007_agent_backup_plan_days.py"


def test_plan_days_are_added_by_a_forward_only_migration():
    base_text = BASE_PLAN_MIGRATION.read_text(encoding="utf-8")
    day_text = DAY_MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "0007"' in day_text
    assert 'down_revision: Union[str, None] = "0006"' in day_text
    assert '"full_days"' in day_text
    assert '"differential_days"' in day_text
    assert '"full_days"' not in base_text
    assert '"differential_days"' not in base_text
