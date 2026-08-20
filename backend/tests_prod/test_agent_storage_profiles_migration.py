from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0008_agent_storage_and_profiles.py"
)


def test_agent_storage_and_profiles_use_a_forward_only_migration():
    text = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "0008"' in text
    assert 'down_revision: Union[str, None] = "0007"' in text
    assert '"origin_snapshot"' in text
    assert '"encryption_public_key"' in text
    assert '"last_heartbeat_at"' in text
    assert '"desired_config_revision"' in text
    assert '"applied_config_revision"' in text
    assert '"health_status"' in text
    assert '"agent_volume_states"' in text
    assert '"agent_storage_alerts"' in text
    assert '"agent_connection_profiles"' in text
    assert "postgresql_where" in text
