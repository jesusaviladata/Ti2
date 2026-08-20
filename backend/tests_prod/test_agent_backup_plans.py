import pytest

from app.core.errors import DomainError
from app.models.operations import AgentBackupPlan
from app.services.agent_backup_scheduler import validate_backup_days


def test_weekly_plan_requires_full_and_keeps_days_exclusive():
    with pytest.raises(DomainError) as missing_full:
        validate_backup_days([], [1, 3])
    assert missing_full.value.code == "BACKUP_PLAN_FULL_REQUIRED"

    with pytest.raises(DomainError) as conflict:
        validate_backup_days([0, 2], [2, 4])
    assert conflict.value.code == "BACKUP_PLAN_DAY_CONFLICT"

    assert validate_backup_days([4, 0, 2, 2], [1, 3]) == ([0, 2, 4], [1, 3])


def test_agent_plan_is_tenant_and_agent_scoped():
    columns = AgentBackupPlan.__table__.columns
    assert columns["tenant_id"].nullable is False
    assert columns["agent_id"].nullable is False
    assert columns["database_names"].nullable is False
    assert columns["full_days"].nullable is False
    assert columns["differential_days"].nullable is False
