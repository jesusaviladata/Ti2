from datetime import datetime, timezone

from app.services.cleanup_scheduler import next_run_for_cron


def test_cleanup_next_run_can_be_computed_before_scheduler_start():
    now = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    next_run = next_run_for_cron("0 2 * * *", now)
    assert next_run == datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc)
