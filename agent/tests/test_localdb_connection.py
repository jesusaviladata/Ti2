import pytest

from agent.data_express_agent.backup import BackupError, _connection_string


@pytest.mark.parametrize("server", [r"(localdb)\MSSQLLocalDB", r"(LOCALDB)\Pruebas QA"])
def test_localdb_uses_local_windows_connection(server):
    connection = _connection_string({"server": server})
    assert "Encrypt=no;" in connection
    assert "Trusted_Connection=yes;" in connection


@pytest.mark.parametrize("server", [r"SQL-PROD\PRINCIPAL", "localhost", "tcp:sql.example.com,1433", r"localdb.example.com\MSSQLLocalDB", r"(localdb)\foo\bar"])
def test_network_and_ambiguous_targets_keep_encryption(server):
    connection = _connection_string({"server": server, "encrypt": False})
    assert "Encrypt=yes;" in connection
    assert "Encrypt=no;" not in connection


def test_localdb_cannot_inject_other_connection_options():
    with pytest.raises(BackupError):
        _connection_string({"server": r"(localdb)\MSSQLLocalDB;Server=remote"})
