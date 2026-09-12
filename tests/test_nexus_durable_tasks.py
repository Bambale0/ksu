from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.db.nexus_models import NexusAdminTask
from app.db.session import SessionFactory
from app.providers.nexus import NexusTask
from app.services import nexus_admin_tasks as nexus_tasks_module
from app.services.nexus_admin_tasks import NexusAdminTaskService, utcnow


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, object]]] = []

    async def download(self, _file_id: str, destination: object) -> None:
        destination.write(b"fake-image")  # type: ignore[attr-defined]

    async def send_photo(self, **kwargs: object) -> object:
        self.sent.append(("photo", kwargs))
        return SimpleNamespace(message_id=777)

    async def send_message(self, **kwargs: object) -> object:
        self.sent.append(("message", kwargs))
        return SimpleNamespace(message_id=778)


class _FakeNexus:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    async def create_nano_banana_pro(self, **kwargs: object) -> str:
        assert str(kwargs["idempotency_key"]).startswith("nexus-regression:")
        image_urls = kwargs["image_urls"]
        assert isinstance(image_urls, list)
        assert str(image_urls[0]).startswith("data:image/jpeg;base64,")
        return "provider-task-1"

    async def get_task(self, task_id: str) -> NexusTask:
        assert task_id == "provider-task-1"
        return NexusTask(
            task_id=task_id,
            status="completed",
            image_urls=["https://example.test/result.png"],
        )

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_nexus_admin_task_recovers_after_lease_and_delivers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nexus_tasks_module, "NexusClient", _FakeNexus)
    bot = _FakeBot()
    idempotency_key = f"nexus-regression:{uuid.uuid4()}"

    async with SessionFactory() as session:
        job = await NexusAdminTaskService.enqueue(
            session,
            telegram_id=123456789,
            chat_id=123456789,
            prompt="durable nexus regression",
            references=[{"file_id": "file-1", "mime_type": "image/jpeg", "file_size": 10}],
            aspect_ratio="1:1",
            image_size="2K",
            idempotency_key=idempotency_key,
        )
        await session.commit()
        job_id = job.id

    async with SessionFactory() as session:
        claimed = await NexusAdminTaskService.claim(session)
    assert claimed == job_id

    async with SessionFactory() as session:
        duplicate_claim = await NexusAdminTaskService.claim(session)
    assert duplicate_claim is None

    # Simulate a worker dying after claim. Once the lease expires, another worker
    # must recover the same durable row instead of losing the provider request.
    async with SessionFactory() as session:
        row = await session.get(NexusAdminTask, job_id, with_for_update=True)
        assert row is not None
        row.lease_until = utcnow() - timedelta(seconds=1)
        row.available_at = utcnow()
        await session.commit()

    async with SessionFactory() as session:
        recovered = await NexusAdminTaskService.claim(session)
    assert recovered == job_id

    await NexusAdminTaskService.process(job_id, bot)  # type: ignore[arg-type]
    async with SessionFactory() as session:
        row = await session.get(NexusAdminTask, job_id)
        assert row is not None
        assert row.status == "generating"
        assert row.external_id == "provider-task-1"
        row.available_at = utcnow()
        await session.commit()

    async with SessionFactory() as session:
        polled = await NexusAdminTaskService.claim(session)
    assert polled == job_id
    await NexusAdminTaskService.process(job_id, bot)  # type: ignore[arg-type]

    async with SessionFactory() as session:
        row = await session.get(NexusAdminTask, job_id)
        assert row is not None
        assert row.status == "delivering"
        assert row.result_url == "https://example.test/result.png"

    async with SessionFactory() as session:
        delivery = await NexusAdminTaskService.claim(session)
    assert delivery == job_id
    await NexusAdminTaskService.process(job_id, bot)  # type: ignore[arg-type]

    async with SessionFactory() as session:
        row = await session.get(NexusAdminTask, job_id)
        assert row is not None
        assert row.status == "succeeded"
        assert row.result_url == "https://example.test/result.png"

    assert len(bot.sent) == 1
    assert bot.sent[0][0] == "photo"
