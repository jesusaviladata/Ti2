from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.file_backup_scheduler import due_slot, dispatch_file_backups

UTC = timezone.utc


def test_due_slot_uses_mexico_timezone_and_rejects_time_before_creation():
    schedule = {'weekdays':[3], 'localTime':'10:30'}
    created = datetime(2026,10,15,15,0,tzinfo=UTC)
    assert due_slot(schedule,'America/Mexico_City',created,datetime(2026,10,15,16,29,tzinfo=UTC)) is None
    assert due_slot(schedule,'America/Mexico_City',created,datetime(2026,10,15,16,31,tzinfo=UTC)) == datetime(2026,10,15,16,30,tzinfo=UTC)
    assert due_slot(schedule,'America/Mexico_City',datetime(2026,10,15,17,0,tzinfo=UTC),datetime(2026,10,15,17,1,tzinfo=UTC)) is None


def test_due_slot_coalesces_missed_weekdays_to_most_recent():
    assert due_slot({'weekdays':[0,3],'localTime':'02:00'},'America/Mexico_City',datetime(2026,10,1,tzinfo=UTC),datetime(2026,10,16,15,tzinfo=UTC)) == datetime(2026,10,15,8,tzinfo=UTC)


@pytest.mark.asyncio
@pytest.mark.parametrize('already_dispatched',[True,False])
async def test_dispatch_deduplicates_persistent_slots_and_commits_run(monkeypatch, already_dispatched):
    from app.services import file_backup_scheduler as module
    now = datetime(2026,10,15,16,31,tzinfo=UTC)
    class Clock(datetime):
        @staticmethod
        def now(zone): return now
    monkeypatch.setattr(module,'datetime',Clock)
    task = SimpleNamespace(id='task',tenant_id='tenant',is_active=True,schedule={'weekdays':[3],'localTime':'10:30'},timezone_name='America/Mexico_City',created_at=datetime(2026,10,15,15,tzinfo=UTC),missed_run_policy='run_once')
    results = [MagicMock(),MagicMock(),MagicMock()]
    results[0].scalars.return_value = ['task']
    results[1].scalar_one_or_none.return_value = task
    results[2].scalar_one_or_none.return_value = 'existing' if already_dispatched else None
    db = SimpleNamespace(execute=AsyncMock(side_effect=results),commit=AsyncMock())
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(module,'AsyncSessionLocal',lambda:context)
    run = SimpleNamespace(summary={'requestedStrategy':'incremental'})
    service = SimpleNamespace(repository=SimpleNamespace(active_run=AsyncMock(return_value=None),get_run=AsyncMock(return_value=run)),create_run=AsyncMock(return_value={'id':'run'}))
    monkeypatch.setattr(module,'FileBackupService',lambda session:service)
    await dispatch_file_backups()
    if already_dispatched:
        service.create_run.assert_not_called()
        db.commit.assert_not_called()
    else:
        service.create_run.assert_awaited_once()
        assert run.summary['scheduledFor'] == '2026-10-15T16:30:00+00:00'
        db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_completion_preserves_schedule_marker_to_prevent_redispatch():
    from app.services.agent_command_service import AgentCommandService
    service = AgentCommandService.__new__(AgentCommandService)
    run = SimpleNamespace(summary={'trigger':'scheduled','scheduledFor':'2026-10-15T16:30:00+00:00'},files_processed=0,bytes_processed=0,chain_id=None)
    service._file_run_for_command = AsyncMock(return_value=run)
    service._file_restore_for_command = AsyncMock(return_value=None)
    await service._project_file_complete(SimpleNamespace(),{'status':'completed','summary':{'filesCopied':2,'bytesCopied':32}},datetime.now(UTC))
    assert run.summary['scheduledFor'] == '2026-10-15T16:30:00+00:00'
    assert run.files_processed == 2
