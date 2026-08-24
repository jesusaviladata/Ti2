import inspect

from app.api.v1 import file_backups
from app.core.database import get_db


def test_task_crud_handlers_use_database_dependency_instead_of_placeholder():
    for endpoint in (
        file_backups.list_tasks,
        file_backups.create_task,
        file_backups.get_task,
        file_backups.update_task,
        file_backups.delete_task,
        file_backups.update_artifact,
    ):
        parameters = inspect.signature(endpoint).parameters
        assert "db" in parameters
        assert parameters["db"].default.dependency is get_db
        assert "_not_ready" not in endpoint.__code__.co_names


def test_backup_execution_endpoints_use_the_managed_agent_protocol():
    for endpoint in (
        file_backups.create_simulation,
        file_backups.create_run,
        file_backups.list_runs,
        file_backups.get_run,
        file_backups.get_simulation,
    ):
        parameters = inspect.signature(endpoint).parameters
        assert "db" in parameters
        assert parameters["db"].default.dependency is get_db
        assert "_not_ready" not in endpoint.__code__.co_names


def test_restore_and_cancellation_remain_closed_until_safe_agent_support_exists():
    for endpoint in (
        file_backups.cancel_run,
        file_backups.create_restore,
        file_backups.confirm_restore,
    ):
        assert "_not_ready" in endpoint.__code__.co_names
