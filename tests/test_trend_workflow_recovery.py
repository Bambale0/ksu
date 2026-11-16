from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.trend_workflow_recovery import TrendWorkflowRecoveryService


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


def _step_and_generation(*, step_kind="image", generation_status="succeeded"):
    user_id = uuid.uuid4()
    run = SimpleNamespace(id=uuid.uuid4(), user_id=user_id, status="running")
    generation = SimpleNamespace(id=uuid.uuid4(), user_id=user_id, status=generation_status)
    step = SimpleNamespace(
        id=uuid.uuid4(), workflow_id=run.id, ordinal=0 if step_kind == "image" else 1,
        kind=step_kind, status="queued",
    )
    return step, generation, run


@pytest.mark.asyncio
async def test_ready_photo_persists_without_starting_video():
    step, generation, run = _step_and_generation()
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_Rows([(step, generation)])),
        get=AsyncMock(return_value=run),
        scalar=AsyncMock(side_effect=[uuid.uuid4(), uuid.uuid4()]),
        commit=AsyncMock(),
    )
    stats = await TrendWorkflowRecoveryService.reconcile_once(session)
    assert stats == {"inspected": 1, "ready": 1, "failed": 0, "deferred": 0}
    assert step.status == "ready"
    assert run.status == "step1_ready"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_succeeded_generation_without_ingested_media_is_not_ready():
    step, generation, run = _step_and_generation()
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_Rows([(step, generation)])),
        get=AsyncMock(return_value=run),
        scalar=AsyncMock(return_value=None),
        commit=AsyncMock(),
    )
    stats = await TrendWorkflowRecoveryService.reconcile_once(session)
    assert stats["deferred"] == 1
    assert step.status == "queued"
    assert run.status == "running"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_generation_marks_step_failed_without_changing_billing():
    step, generation, run = _step_and_generation(step_kind="video", generation_status="failed")
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_Rows([(step, generation)])),
        get=AsyncMock(return_value=run),
        scalar=AsyncMock(),
        commit=AsyncMock(),
    )
    stats = await TrendWorkflowRecoveryService.reconcile_once(session)
    assert stats["failed"] == 1
    assert step.status == "failed"
    assert run.status == "failed"
    session.scalar.assert_not_awaited()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_generation_does_not_override_terminal_run():
    step, generation, run = _step_and_generation(
        step_kind="video", generation_status="failed"
    )
    run.status = "completed"
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_Rows([(step, generation)])),
        get=AsyncMock(return_value=run),
        scalar=AsyncMock(),
        commit=AsyncMock(),
    )
    stats = await TrendWorkflowRecoveryService.reconcile_once(session)
    assert stats["failed"] == 1
    assert step.status == "failed"
    assert run.status == "completed"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_refuses_generation_from_different_user():
    step, generation, run = _step_and_generation()
    generation.user_id = uuid.uuid4()
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_Rows([(step, generation)])),
        get=AsyncMock(return_value=run),
        scalar=AsyncMock(),
        commit=AsyncMock(),
    )
    stats = await TrendWorkflowRecoveryService.reconcile_once(session)
    assert stats["deferred"] == 1
    assert step.status == "queued"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_completed_video_marks_workflow_complete():
    step, generation, run = _step_and_generation(step_kind="video")
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_Rows([(step, generation)])),
        get=AsyncMock(return_value=run),
        scalar=AsyncMock(return_value=uuid.uuid4()),
        commit=AsyncMock(),
    )
    result = await TrendWorkflowRecoveryService.reconcile_once(session)
    assert result["ready"] == 1
    assert step.status == "ready"
    assert run.status == "completed"


@pytest.mark.asyncio
async def test_recovery_limit_rejects_unbounded_scans():
    session = SimpleNamespace()
    with pytest.raises(ValueError, match="limit"):
        await TrendWorkflowRecoveryService.reconcile_once(session, limit=0)
    with pytest.raises(ValueError, match="limit"):
        await TrendWorkflowRecoveryService.reconcile_once(session, limit=101)