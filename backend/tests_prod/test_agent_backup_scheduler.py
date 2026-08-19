from datetime import datetime, timezone

from app.services.agent_backup_scheduler import (
    backup_type_for_weekday,
    next_run_for_plan,
)


def test_weekday_policy_uses_full_and_differential_backups():
    assert backup_type_for_weekday(0) == "full"
    assert backup_type_for_weekday(1) == "differential"
    assert backup_type_for_weekday(2) == "full"
    assert backup_type_for_weekday(3) == "differential"
    assert backup_type_for_weekday(4) == "full"
    assert backup_type_for_weekday(5) is None
    assert backup_type_for_weekday(6) is None


def test_plan_next_run_uses_mexico_city_local_time():
    # Monday 2026-08-17 at noon UTC. Next 02:00 CDMX occurrence is Tuesday 08:00 UTC.
    now = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)

    next_run = next_run_for_plan("02:00", "America/Mexico_City", now)

    assert next_run is not None
    assert next_run.astimezone(timezone.utc) == datetime(
        2026, 8, 18, 8, 0, tzinfo=timezone.utc
    )
