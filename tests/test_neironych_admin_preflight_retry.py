from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import uuid

import pytest

from app.providers.neironych_video import NeironychProviderError
from app.services.seedance_admin_tasks import SeedanceAdminTaskService


@pytest.mark.asyncio
@pytest.mark.parametrize("new_protocol", [False, True])
async def test_only_new_queued_preflight_can_retry_without_wire_snapshot(monkeypatch, new_protocol):
    payload = {
        "prompt": "A calm scene",
        "duration": 4,
        "resolution": "480p",
        "aspect_ratio": "9:16",
    }
    if new_protocol:
        payload["_neironych_wire_version"] = 1
    task = SimpleNamespace(
        id=uuid.uuid4(),
        status="queued",
        external_id=None,
        model_name="seedance-2.5",
        request_payload=payload,
        attempts=1,
        idempotency_key="admin-preflight-stable-key",
    )
    posted = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return task

        async def commit(self):
            return None

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def aclose(self):
            pass

        async def list_models(self):
            return ["seedance-2.5"]

        async def create_video(self, **kwargs):
            posted.append(kwargs)
            assert task.status == "submitting"
            assert (
                task.request_payload["_neironych_submission"]["body_json"] == kwargs["request_body"]
            )
            return "preflight-recovered-id"

    monkeypatch.setattr("app.services.seedance_admin_tasks.SessionFactory", Session)
    monkeypatch.setattr("app.services.seedance_admin_tasks.NeironychVideoClient", Client)
    monkeypatch.setattr("app.services.seedance_admin_tasks.validate_reference_payload", AsyncMock())
    if new_protocol:
        await SeedanceAdminTaskService._submit(task.id)
        assert len(posted) == 1
        assert task.status == "generating" and task.external_id == "preflight-recovered-id"
        assert posted[0]["idempotency_key"] == "admin-preflight-stable-key"
        assert "_neironych_wire_version" not in json.loads(posted[0]["request_body"])
    else:
        with pytest.raises(NeironychProviderError, match="Original admin request body unavailable"):
            await SeedanceAdminTaskService._submit(task.id)
        assert not posted


@pytest.mark.asyncio
async def test_enqueue_sets_private_protocol_version_without_mutating_input():
    captured = {}

    class Result:
        def scalar_one_or_none(self):
            return captured["id"]

    class Session:
        async def execute(self, statement):
            captured.update(statement.compile().params)
            return Result()

        async def get(self, model, task_id):
            return SimpleNamespace(id=task_id, request_payload=captured["request_payload"])

    original = {"prompt": "test", "_neironych_wire_version": 0}
    result = await SeedanceAdminTaskService.enqueue(
        Session(),
        telegram_id=1,
        chat_id=1,
        model_name="seedance-2.5",
        request_payload=original,
        idempotency_key="admin-enqueue-test-key",
    )
    assert result.request_payload["_neironych_wire_version"] == 1
    assert original["_neironych_wire_version"] == 0
