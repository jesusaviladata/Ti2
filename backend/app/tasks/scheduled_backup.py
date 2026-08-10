"""Backward-compatible import for the APScheduler backup job."""

from app.services.backup_runtime_service import _run_scheduled_backup as run_scheduled_backup
