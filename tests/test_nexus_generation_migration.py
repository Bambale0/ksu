from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.providers.nexus import NANO_BANANA_MODELS, NexusClient, NexusProviderError
from app.services.model_catalog import InvalidModelParametersError, ModelCatalog
from app.services.model_spec_image_audit import install_model_spec_image_audit
from app.services.model_ui_contract import build_public_model_ui_schema
from app.services.nexus_generation_provider import NexusGenerationProviderService


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["nano-banana-pro", "nano-banana-2"])
async def test_nexus_client_submits_both_migrated_models(model_name: str) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/generate"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.headers["Idempotency-Key"] == "generation:123"
        captured.update(json.loads(request.content))
        return httpx.Response(202, json={"task_id": f"task-{model_name}"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://nexusapi.dev",
    ) as http_client:
        client = NexusClient("test-key", client=http_client)
        task_id = await client.create_nano_banana(
            model_name=model_name,
            prompt=" prompt ",
            aspect_ratio="9:16",
            image_size="4K",
            image_urls=["https://example.test/a.jpg", "https://example.test/a.jpg"],
            idempotency_key="generation:123",
        )

    assert task_id == f"task-{model_name}"
    assert captured == {
        "params": {
            "model_name": model_name,
            "prompt": "prompt",
            "aspect_ratio": "9:16",
            "image_size": "4K",
            "image_urls": ["https://example.test/a.jpg"],
        }
    }


def test_nexus_generation_normalizes_legacy_roxy_payload() -> None:
    normalized = NexusGenerationProviderService._normalize_input(
        "nano-banana-2",
        {
            "prompt": "edit the reference",
            "image_input": ["https://example.test/ref.jpg"],
            "aspect_ratio": "4:5",
            "resolution": "2k",
            "output_format": "png",
        },
    )
    assert normalized == {
        "prompt": "edit the reference",
        "aspect_ratio": "4:5",
        "image_size": "2K",
        "image_urls": ["https://example.test/ref.jpg"],
    }


def test_nexus_generation_migration_is_limited_to_pro_and_v2() -> None:
    assert NANO_BANANA_MODELS == frozenset({"nano-banana-pro", "nano-banana-2"})
    assert "nano-banana-2-lite" not in NexusGenerationProviderService.MODEL_IDS


@pytest.mark.asyncio
async def test_nexus_client_fails_closed_above_documented_reference_limit() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
        base_url="https://nexusapi.dev",
    ) as http_client:
        client = NexusClient("test-key", client=http_client)
        with pytest.raises(NexusProviderError, match="at most 4 references"):
            await client.create_nano_banana(
                model_name="nano-banana-2",
                prompt="refs",
                image_urls=[f"https://example.test/{index}.jpg" for index in range(5)],
            )


def test_public_nexus_contract_rejects_bad_inputs_before_generation_is_charged() -> None:
    install_model_spec_image_audit()

    with pytest.raises(InvalidModelParametersError, match="at most four"):
        ModelCatalog.prepare(
            "nano-banana-2",
            {
                "prompt": "refs",
                "image_input": [f"https://example.test/{index}.jpg" for index in range(5)],
                "aspect_ratio": "1:1",
                "resolution": "1K",
            },
        )

    with pytest.raises(InvalidModelParametersError, match="aspect_ratio"):
        ModelCatalog.prepare(
            "nano-banana-2",
            {
                "prompt": "ratio",
                "image_input": [],
                "aspect_ratio": "1:4",
                "resolution": "1K",
            },
        )


@pytest.mark.parametrize("model_id", ["nano-banana-pro", "nano-banana-2"])
def test_public_nexus_ui_matches_provider_capabilities(model_id: str) -> None:
    install_model_spec_image_audit()
    schema = build_public_model_ui_schema(ModelCatalog.get(model_id).public_dict())
    fields = {str(field["name"]): field for field in schema["fields"]}

    assert fields["image_input"]["max_items"] == 4
    assert "output_format" not in fields
    assert fields["aspect_ratio"]["suggestions"] == [
        "auto",
        "1:1",
        "2:3",
        "3:2",
        "3:4",
        "4:3",
        "4:5",
        "5:4",
        "9:16",
        "16:9",
        "21:9",
    ]
    assert fields["resolution"]["suggestions"] == ["1K", "2K", "4K"]
    assert "output_format" not in schema["defaults"]


@pytest.mark.asyncio
async def test_uncertain_nexus_create_is_requeued_for_idempotent_replay() -> None:
    generation = SimpleNamespace(
        status="submitting",
        error=None,
        updated_at=None,
        provider="nexus",
        parameters={},
    )

    class StubSession:
        committed = False

        async def scalar(self, _statement):
            return generation

        async def commit(self) -> None:
            self.committed = True

    session = StubSession()
    request = httpx.Request("POST", "https://nexusapi.dev/generate")
    exc = httpx.ReadTimeout("response lost", request=request)

    await NexusGenerationProviderService._record_submission_error(
        session,  # type: ignore[arg-type]
        uuid.uuid4(),
        exc,
    )

    assert session.committed is True
    assert generation.status == "retry"
    assert generation.provider == "nexus"
    assert generation.parameters["_submission_uncertain"] is True
    assert generation.parameters["_submission_uncertain_at"]


def test_generation_worker_dispatches_and_recovers_nexus_separately_from_kie() -> None:
    source = Path("app/services/generation_worker.py").read_text(encoding="utf-8")
    assert 'provider == "nexus"' in source
    assert "NexusGenerationProviderService.submit" in source
    assert "NexusGenerationProviderService.sync_task" in source
    assert 'Generation.provider.in_(_PROVIDER_NAMES)' in source
    assert 'AbuseProtectionService.provider_submission_gate(redis, provider)' in source
    assert 'record_provider_success(redis, provider)' in source
