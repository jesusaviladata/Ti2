"""Backward-compatible import for the APScheduler cleanup job."""

from app.services.cleanup_scheduler import run_cleanup_schedule as run_scheduled_cleanup
