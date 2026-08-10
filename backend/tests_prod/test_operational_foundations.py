from app.core.capabilities import Capability, capabilities_for, has_capabilities
from app.core.redaction import redact
from app.models.user import UserRole


def test_admin_inherits_every_capability():
    assert capabilities_for(UserRole.admin) == frozenset(Capability)
    assert has_capabilities(UserRole.admin, *Capability)


def test_client_is_read_only():
    assert has_capabilities(UserRole.client, Capability.DASHBOARD_READ)
    assert has_capabilities(UserRole.client, Capability.REPORT_READ)
    assert not has_capabilities(UserRole.client, Capability.BACKUP_RUN)
    assert not has_capabilities(UserRole.client, Capability.PURGE)


def test_operator_roles_can_execute_reversible_work_but_not_purge():
    for role in (UserRole.technician, UserRole.supervisor):
        assert has_capabilities(role, Capability.CLEANUP_SIMULATE)
        assert has_capabilities(role, Capability.CLEANUP_EXECUTE)
        assert not has_capabilities(role, Capability.PURGE)


def test_recursive_redaction_removes_credentials_without_changing_safe_values():
    value = {
        "server": "db.internal",
        "password": "secret",
        "nested": {
            "privateKey": "pem-data",
            "items": [{"passphrase": "hidden"}, {"name": "safe"}],
        },
    }

    assert redact(value) == {
        "server": "db.internal",
        "password": "***",
        "nested": {
            "privateKey": "***",
            "items": [{"passphrase": "***"}, {"name": "safe"}],
        },
    }
