from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0011_file_backup_module.py"
)


def _migration_text() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_file_backup_migration_is_chained_from_current_head():
    text = _migration_text()

    assert 'revision: str = "0011"' in text
    assert 'down_revision: Union[str, None] = "0010"' in text


def test_file_backup_migration_creates_administrative_tables_only():
    text = _migration_text()
    expected_tables = {
        "file_backup_tasks",
        "file_backup_sources",
        "file_backup_filters",
        "file_backup_runs",
        "file_backup_chains",
        "file_backup_artifacts",
        "file_restore_jobs",
        "file_restore_confirmations",
    }

    for table_name in expected_tables:
        assert f'"{table_name}"' in text

    assert '"file_backup_files"' not in text
    assert '"file_catalog_entries"' not in text


def test_file_backup_migration_has_tenant_state_and_history_indexes():
    text = _migration_text()

    for fragment in (
        "ix_file_backup_tasks_tenant_active",
        "ix_file_backup_runs_tenant_status_created",
        "ix_file_backup_artifacts_tenant_created",
        "ix_file_restore_jobs_tenant_status_created",
        "uq_file_backup_source_task_path",
        "uq_file_backup_filter_task_rule",
    ):
        assert fragment in text


def test_file_backup_migration_downgrade_removes_every_created_table():
    text = _migration_text()
    downgrade = text.split("def downgrade() -> None:", maxsplit=1)[1]

    for table_name in (
        "file_restore_confirmations",
        "file_restore_jobs",
        "file_backup_artifacts",
        "file_backup_runs",
        "file_backup_chains",
        "file_backup_filters",
        "file_backup_sources",
        "file_backup_tasks",
    ):
        assert f'op.drop_table("{table_name}")' in downgrade
