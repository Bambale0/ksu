from __future__ import annotations

import random
from decimal import Decimal

import pytest

import app.services.generation_provider as generation_provider_module
from app.core.config import settings
from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.providers.nexus import NexusTask
from app.services.generation_provider import GenerationProviderService
from app.services.provider_media_transport import ProviderMediaTransport


class FakeNexusClient:
    created: list[dict[str, object]] = []
    task: NexusTask | None = None

    def __init__(self, api_key: str, base_url: str) -> None:
        assert api_key == "nexus-test-key"
        assert base_url == "https://nexus.test"

    async def aclose(self) -> None:
        return None

    async def create_nano_banana(self, **kwargs: object) -> str:
        self.created.append(dict(kwargs))
        return "nexus-task-123"

    async def get_task(self, task_id: str) -> NexusTask:
        assert task_id == "nexus-task-123"
        assert self.task is not None
        return self.task


@pytest.fixture(autouse=True)
def _reset_fake_nexus(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeNexusClient.created = []
    FakeNexusClient.task = None
    monkeypatch.setattr(generation_provider_module, "NexusClient", FakeNexusClient)
    monkeypatch.setattr(settings, "nexus_api_key", "nexus-test-key")
    monkeypatch.setattr(settings, "nexus_api_base_url", "https://nexus.test")


async def _user(session, name: str) -> User:
    user = User(
        telegram_id=random.randint(7_000_000_000_000, 7_999_999_999_999),
        first_name=name,
    )
    session.add(user)
    await session.flush()
    return user


def test_target_provider_routes_only_migrated_nano_models_to_nexus() -> None:
    assert GenerationProviderService.target_provider(
        Generation(parameters={"_model_id": "nano-banana-pro"})
    ) == "nexus"
    assert GenerationProviderService.target_provider(
        Generation(parameters={"_model_id": "nano-banana-2"})
    ) == "nexus"
    assert GenerationProviderService.target_provider(
        Generation(parameters={"_model_id": "nano-banana-2-lite"})
    ) == "kie"
    assert GenerationProviderService.target_provider(
        Generation(parameters={"_model_id": "seedream-4.5-edit"})
    ) == "kie"


@pytest.mark.asyncio
@pytest.mark.parametrize("model_id", ["nano-banana-pro", "nano-banana-2"])
async def test_submit_routes_migrated_nano_models_to_nexus_without_kie_upload(
    monkeypatch: pytest.MonkeyPatch,
    model_id: str,
) -> None:
    async def forbidden_kie_upload(_payload: dict[str, object]) -> dict[str, object]:
        raise AssertionError("Nexus-routed generation must not depend on KIE upload transport")

    monkeypatch.setattr(ProviderMediaTransport, "prepare", forbidden_kie_upload)

    refs = [f"https://media.example/ref-{index}.png" for index in range(4)]
    async with SessionFactory() as session:
        user = await _user(session, f"Nexus {model_id}")
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="queued",
            prompt="keep identity and change the background",
            cost_rox=Decimal("0"),
            provider="kie",
            parameters={
                "_model_id": model_id,
                "_provider_model": model_id,
                "image_input": refs,
                "aspect_ratio": "4:5",
                "resolution": "4K",
            },
        )
        session.add(generation)
        await session.commit()

        submitted = await GenerationProviderService.submit(session, generation.id)

        assert submitted.provider == "nexus"
        assert submitted.status == "generating"
        assert submitted.external_id == "nexus-task-123"
        assert submitted.parameters.get("_provider_submitted_at")

    assert FakeNexusClient.created == [
        {
            "model_name": model_id,
            "prompt": "keep identity and change the background",
            "aspect_ratio": "4:5",
            "image_size": "4K",
            "image_urls": refs,
            "idempotency_key": str(generation.id),
        }
    ]


@pytest.mark.asyncio
async def test_sync_nexus_task_reuses_existing_success_lifecycle() -> None:
    FakeNexusClient.task = NexusTask(
        task_id="nexus-task-123",
        status="completed",
        image_urls=["https://cdn.example/nexus-result.png"],
    )

    async with SessionFactory() as session:
        user = await _user(session, "Nexus sync")
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="generating",
            prompt="sync me",
            cost_rox=Decimal("0"),
            provider="nexus",
            external_id="nexus-task-123",
            parameters={
                "_model_id": "nano-banana-pro",
                "_provider_model": "nano-banana-pro",
            },
        )
        session.add(generation)
        await session.commit()

        synced = await GenerationProviderService.sync_nexus_task(
            session,
            task_id="nexus-task-123",
            generation_id=generation.id,
        )

        assert synced is not None
        assert synced.status == "succeeded"
        assert synced.result_url == "https://cdn.example/nexus-result.png"
        assert synced.parameters["_result_urls"] == ["https://cdn.example/nexus-result.png"]
