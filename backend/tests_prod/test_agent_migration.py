from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0004_windows_agents.py"


def test_agent_migration_creates_all_durable_tables():
    source = MIGRATION.read_text(encoding="utf-8")

    for table in (
        "remote_agents",
        "agent_pairing_tokens",
        "agent_request_nonces",
        "agent_commands",
        "remote_structure_validations",
    ):
        assert f'op.create_table(\n        "{table}"' in source


def test_agent_migration_preserves_legacy_transport_and_guards_downgrade():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'server_default="legacy"' in source
    assert "No se puede revertir 0004" in source
    assert "transport = 'agent'" in source

