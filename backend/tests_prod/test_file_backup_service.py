from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.errors import DomainError
from app.models.file_backup import FileBackupArtifact
from app.schemas.file_backup import (
    FileBackupTaskCreate,
    FileBackupTaskUpdate,
)
from app.services.file_backup_service import FileBackupService


TENANT_ID = str(uuid.uuid4())
AGENT_ID = uuid.uuid4()
PROFILE_ID = uuid.uuid4()


def _agent(*, status: str = "connected", capabilities=None):
    return SimpleNamespace(
        id=AGENT_ID,
        tenant_id=uuid.UUID(TENANT_ID),
        status=status,
        revoked_at=None,
        metadata_json={
            "capabilities": capabilities
            if capabilities is not None
            else ["file_backup_v1"]
        },
    )


def _profile(*, agent_id=AGENT_ID, sync_status="applied", active=True):
    return SimpleNamespace(
        id=PROFILE_ID,
        agent_id=agent_id,
        profile_type="destination",
        sync_status=sync_status,
        is_active=active,
    )


def _payload() -> FileBackupTaskCreate:
    return FileBackupTaskCreate.model_validate(
        {
            "name": "Documentos Core",
            "agentId": AGENT_ID,
            "destinationProfileId": PROFILE_ID,
            "sources": [{"path": r"D:\Core"}],
            "filters": [
                {"kind": "exclude", "operator": "glob", "pattern": "*.tmp"}
            ],
            "strategy": "incremental",
            "format": "direct",
            "schedule": {"weekdays": [0, 2, 4], "localTime": "02:00"},
        }
    )


class FakeDb:
    def __init__(self):
        self.flushed = 0

    async def flush(self):
        self.flushed += 1


class FakeAgents:
    def __init__(self, agent=None):
        self.agent = agent if agent is not None else _agent()

    async def get_agent(self, tenant_id, agent_id):
        assert tenant_id == TENANT_ID
        assert str(agent_id) == str(AGENT_ID)
        return self.agent


class FakeProfiles:
    def __init__(self, profile=None):
        self.profile = profile if profile is not None else _profile()

    async def get(self, tenant_id, agent_id, profile_id):
        assert tenant_id == TENANT_ID
        assert agent_id == AGENT_ID
        assert str(profile_id) == str(PROFILE_ID)
        return self.profile


class FakeRepository:
    def __init__(self):
        self.tasks = {}
        self.sources = {}
        self.filters = {}
        self.deleted = []
        self.history = set()
        self.artifact = None
        self.last_list = None

    def add_task(self, task):
        self.tasks[task.id] = task

    def add_source(self, source):
        self.sources.setdefault(source.task_id, []).append(source)

    def add_filter(self, item):
        self.filters.setdefault(item.task_id, []).append(item)

    async def replace_sources(self, task, sources):
        self.sources[task.id] = list(sources)

    async def replace_filters(self, task, filters):
        self.filters[task.id] = list(filters)

    async def components(self, tenant_id, task_ids):
        assert tenant_id == TENANT_ID
        return (
            {task_id: self.sources.get(task_id, []) for task_id in task_ids},
            {task_id: self.filters.get(task_id, []) for task_id in task_ids},
        )

    async def get_task(self, tenant_id, task_id):
        assert tenant_id == TENANT_ID
        return self.tasks.get(uuid.UUID(str(task_id)))

    async def list_tasks(self, tenant_id, **filters):
        assert tenant_id == TENANT_ID
        self.last_list = filters
        items = list(self.tasks.values())
        return items, len(items)

    async def has_history(self, tenant_id, task_id):
        assert tenant_id == TENANT_ID
        return task_id in self.history

    async def delete_task(self, task):
        self.deleted.append(task.id)
        self.tasks.pop(task.id, None)

    async def get_artifact(self, tenant_id, artifact_id):
        assert tenant_id == TENANT_ID
        if self.artifact and self.artifact.id == uuid.UUID(str(artifact_id)):
            return self.artifact
        return None


def _service(*, agent=None, profile=None, repo=None):
    repository = repo or FakeRepository()
    return (
        FileBackupService(
            FakeDb(),
            repository=repository,
            agents=FakeAgents(agent),
            profiles=FakeProfiles(profile),
        ),
        repository,
    )


@pytest.mark.asyncio
async def test_create_is_tenant_scoped_revisioned_and_serialized_without_secrets():
    service, repo = _service()

    result = await service.create(TENANT_ID, _payload())

    task = next(iter(repo.tasks.values()))
    assert task.tenant_id == uuid.UUID(TENANT_ID)
    assert task.agent_id == AGENT_ID
    assert task.config_revision == 1
    assert result["firstRunWillBeFull"] is True
    assert result["sources"] == [{"path": r"D:\Core", "includeSubfolders": True}]
    assert "secret" not in result
    assert "secretEnvelope" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent", "code"),
    [
        (_agent(status="revoked"), "AGENT_REVOKED"),
        (_agent(capabilities=[]), "AGENT_FILE_BACKUP_UNSUPPORTED"),
    ],
)
async def test_create_rejects_revoked_or_unsupported_agent(agent, code):
    service, _ = _service(agent=agent)

    with pytest.raises(DomainError) as rejected:
        await service.create(TENANT_ID, _payload())

    assert rejected.value.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile",
    [
        _profile(agent_id=uuid.uuid4()),
        _profile(sync_status="pending"),
        _profile(active=False),
    ],
)
async def test_create_requires_applied_destination_on_same_agent(profile):
    service, _ = _service(profile=profile)

    with pytest.raises(DomainError) as rejected:
        await service.create(TENANT_ID, _payload())

    assert rejected.value.code == "FILE_BACKUP_DESTINATION_INVALID"


@pytest.mark.asyncio
async def test_offline_update_increments_revision_without_requiring_liveness():
    service, repo = _service(agent=_agent(status="offline"))
    created = await service.create(TENANT_ID, _payload())

    updated = await service.update(
        TENANT_ID,
        created["id"],
        FileBackupTaskUpdate(name="Documentos Core Actualizados"),
    )

    assert updated["name"] == "Documentos Core Actualizados"
    assert updated["configRevision"] == 2


@pytest.mark.asyncio
async def test_delete_with_history_deactivates_instead_of_deleting():
    service, repo = _service()
    created = await service.create(TENANT_ID, _payload())
    task_id = uuid.UUID(created["id"])
    repo.history.add(task_id)

    result = await service.delete(TENANT_ID, task_id)

    assert result == "deactivated"
    assert repo.tasks[task_id].is_active is False
    assert repo.tasks[task_id].config_revision == 2
    assert repo.deleted == []


@pytest.mark.asyncio
async def test_list_passes_pagination_and_filters_to_tenant_repository():
    service, repo = _service()
    await service.create(TENANT_ID, _payload())

    result = await service.list(
        TENANT_ID,
        page=2,
        page_size=10,
        agent_id=AGENT_ID,
        active=True,
        search="Core",
    )

    assert repo.last_list == {
        "skip": 10,
        "limit": 10,
        "agent_id": AGENT_ID,
        "active": True,
        "search": "Core",
    }
    assert result["page"] == 2
    assert result["pageSize"] == 10


@pytest.mark.asyncio
async def test_protect_artifact_changes_only_audited_protection_fields():
    service, repo = _service()
    artifact_id = uuid.uuid4()
    artifact = FileBackupArtifact(
        id=artifact_id,
        tenant_id=uuid.UUID(TENANT_ID),
        run_id=uuid.uuid4(),
        chain_id=uuid.uuid4(),
        kind="direct",
        location=r"D:\Backups\2026-08-21",
        manifest_summary={},
        protected=False,
    )
    repo.artifact = artifact
    user_id = uuid.uuid4()

    result = await service.set_artifact_protection(
        TENANT_ID, artifact_id, protected=True, user_id=user_id
    )

    assert artifact.protected is True
    assert artifact.protected_by == user_id
    assert artifact.protected_at is not None
    assert result["protected"] is True
