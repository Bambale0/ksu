from __future__ import annotations

import base64
import json
import io
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.core.config import settings
from app.providers.kie import KieProviderError
from app.services.generation_provider import GenerationProviderService
from app.services.generation_reliability import ClaimedGeneration, GenerationOutboxService
from app.services.abuse_protection import AbuseProtectionService
from app.providers.neironych_submission import SNAPSHOT_KEY
from app.services.generation_provider_routing import configured_routes, route_for_model, route_options
from app.services.neironych_generation_provider import NeironychGenerationProviderService as Service
from app.services.generation_worker import GenerationWorkerService

from app.providers.neironych_errors import NeironychProviderError
from app.providers.neironych_image import NeironychImageClient
from app.providers.neironych_video import NeironychVideoClient


@pytest.mark.parametrize(
    "model,ratio,resolution,refs,expected",
    [
        ("nano-banana-2", "16:9", "2K", [], {"resolution": "2k", "aspect_ratio": "16:9"}),
        ("nano-banana-2-lite", "3:4", "1K", ["https://example.test/ref.png"],
         {"resolution": "1k", "aspect_ratio": "3:4"}),
        ("gpt-image-2", "16:9", "", [], {"size": "1024x576"}),
        ("gpt-image-2", "auto", "", ["https://example.test/ref.png"], {"size": "auto"}),
        ("gpt-image-2", "1:1", "1K", [], {"size": "1024x1024"}),
        ("gpt-image-2", "16:9", "2K", [], {"size": "2048x1152"}),
        ("gpt-image-2", "9:16", "4K", [], {"size": "2304x4096"}),
    ],
)
async def test_matching_image_models_send_documented_http_contract(
    model, ratio, resolution, refs, expected,
):
    calls = []

    def respond(request):
        calls.append(request)
        assert request.url.path == ("/v1/images/edits" if refs else "/v1/images/generations")
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.headers["Idempotency-Key"] == "contract-image-test"
        body = json.loads(request.content)
        assert body == {
            "model": model, "prompt": "A blue ceramic cup", "n": 1,
            "response_format": "b64_json", **expected,
            **({"images": [{"image_url": refs[0]}]} if refs else {}),
        }
        return httpx.Response(200, headers={"X-Request-Id": "image-test-id"},
                              json={"data": [{"b64_json": base64.b64encode(b"image").decode()}]})

    async with httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(respond)) as http:
        client = NeironychImageClient("test-key", "https://provider.test", client=http)
        result = await client.create_image(
            model=model, prompt="A blue ceramic cup", aspect_ratio=ratio,
            resolution=resolution, image_urls=refs, idempotency_key="contract-image-test",
        )
    assert len(calls) == 1
    assert result.content == b"image" and result.request_id == "image-test-id"


@pytest.mark.parametrize("model,ratio,resolution,refs", [
    ("nano-banana-2", "auto", "1K", []),
    ("nano-banana-2-lite", "1:1", "2K", []),
    ("nano-banana-2", "21:9", "1K", []),
    ("nano-banana-2", "1:1", "1K", [f"https://example.test/{i}.png" for i in range(4)]),
    ("gpt-image-2", "auto", "1K", []),
])
async def test_unrepresentable_image_settings_skip_before_paid_post(model, ratio, resolution, refs):
    def forbidden(_request):
        raise AssertionError("Unsupported capability must not make a paid POST")

    async with httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(forbidden)) as http:
        client = NeironychImageClient("test-key", "https://provider.test", client=http)
        with pytest.raises(NeironychProviderError) as caught:
            await client.create_image(model=model, prompt="A cup", aspect_ratio=ratio,
                                      resolution=resolution, image_urls=refs,
                                      idempotency_key="contract-image-test")
    assert caught.value.local_validation
    assert caught.value.error_code == "capability_mismatch"


@pytest.mark.parametrize("model,expected", [
    ("nano-banana-2", ("nexus", "neironych", "kie")),
    ("nano-banana-2-lite", ("nexus", "neironych", "kie")),
    ("gpt-image-2-t2i", ("nexus", "neironych", "kie")),
    ("gpt-image-2-i2i", ("nexus", "neironych", "kie")),
    ("grok-video-1.5", ("kie", "neironych")),
])
def test_each_new_matching_model_has_neironych_fallback(model, expected):
    assert route_for_model(model) == expected


async def new_generation(model, **inputs):
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Synthetic adapter test")
        session.add(user)
        await session.flush()
        row = Generation(user_id=user.id, kind="generate", provider="neironych", status="queued",
            prompt="A cup", cost_rox=Decimal("0"), parameters={
                "_model_id": model, "_provider_route": ["neironych", "kie"],
                "_provider_route_index": 0, "prompt": "A cup", **inputs,
            })
        session.add(row)
        await session.commit()
        return row.id


@pytest.mark.parametrize("model,refs", [
    ("nano-banana-2", []), ("nano-banana-2-lite", []),
    ("gpt-image-2-t2i", []), ("gpt-image-2-i2i", ["https://example.test/ref.png"]),
])
@pytest.mark.parametrize("source_format", ["PNG", "JPEG"])
async def test_new_image_service_freezes_correct_wire_model_and_stores_real_jpeg(monkeypatch, model, refs, source_format):
    png = io.BytesIO()
    image = Image.new("RGBA", (16, 16), (0, 0, 255, 128))
    if source_format == "JPEG":
        image = image.convert("RGB")
    image.save(png, format=source_format, **({"quality": 97} if source_format == "JPEG" else {}))
    calls = []

    async def respond(request):
        async with SessionFactory() as session:
            row = await session.get(Generation, gid)
            assert row.status == "submitting"
            assert row.parameters[SNAPSHOT_KEY]["body_json"].encode() == request.content
        body = json.loads(request.content)
        calls.append(body)
        assert body["model"] == ("gpt-image-2" if model.startswith("gpt") else model)
        assert request.url.path == ("/v1/images/edits" if refs else "/v1/images/generations")
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png.getvalue()).decode()}]})

    async def complete(_cls, session, generation_id, *, path, content_type, source_url):
        assert content_type == "image/jpeg" and path.suffix == ".jpg"
        with Image.open(path) as image:
            assert image.format == "JPEG" and image.mode == "RGB"
        if source_format == "JPEG":
            assert path.read_bytes() == png.getvalue()  # No extra lossy recompression.
        row = await session.get(Generation, generation_id)
        row.status = "succeeded"
        await session.commit()
        return row

    async with httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(respond)) as http:
        client = NeironychImageClient("test-key", "https://provider.test", client=http)
        monkeypatch.setattr("app.services.neironych_generation_provider.NeironychImageClient", lambda *_: client)
        monkeypatch.setattr(Service, "_complete_local_file", classmethod(complete))
        gid = await new_generation(model, aspect_ratio="1:1", input_urls=refs, resolution="1K")
        async with SessionFactory() as session:
            row = await Service.submit(session, gid)
            assert row.status == "succeeded" and row.external_id is None
            assert GenerationWorkerService._protection_provider(row, "neironych") == "neironych:image"
    assert len(calls) == 1


async def test_grok_service_freezes_provider_alias_and_keeps_accepted_id(monkeypatch):
    upstream_id = "accepted-grok-" + str(uuid.uuid4())
    def respond(request):
        assert json.loads(request.content)["model"] == "grok-imagine-video-1.5"
        return httpx.Response(202, json={"request_id": upstream_id})

    async with httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(respond)) as http:
        client = NeironychVideoClient("test-key", "https://provider.test", client=http)
        monkeypatch.setattr("app.services.neironych_generation_provider.NeironychVideoClient", lambda *_: client)
        gid = await new_generation("grok-video-1.5", duration=2, resolution="480p")
        async with SessionFactory() as session:
            row = await Service.submit(session, gid)
            assert row.provider == "neironych" and row.status == "generating"
            assert row.external_id == upstream_id
            assert row.parameters[SNAPSHOT_KEY]["model"] == "grok-imagine-video-1.5"


@pytest.mark.parametrize("status,expected_provider", [(402, "kie"), (503, "neironych")])
async def test_grok_neironych_primary_only_falls_back_on_definite_rejection(
    monkeypatch, status, expected_provider,
):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {
            "code": "insufficient_balance" if status == 402 else "provider_temporarily_unavailable",
            "message": "Synthetic provider failure",
        }})

    async with httpx.AsyncClient(
        base_url="https://provider.test", transport=httpx.MockTransport(respond),
    ) as http:
        client = NeironychVideoClient("test-key", "https://provider.test", client=http)
        monkeypatch.setattr(
            "app.services.neironych_generation_provider.NeironychVideoClient", lambda *_: client,
        )
        gid = await new_generation("grok-video-1.5", duration=2, resolution="480p")
        async with SessionFactory() as session:
            row = await Service.submit(session, gid)
            assert row.provider == expected_provider and row.status == "retry"
            assert row.external_id is None
            if status == 402:
                assert row.parameters["_provider_route_index"] == 1
                assert row.parameters["_provider_attempts"][0]["provider"] == "neironych"
                assert SNAPSHOT_KEY not in row.parameters
            else:
                assert row.parameters["_provider_route_index"] == 0
                assert row.parameters["_submission_uncertain"]
                assert not row.parameters.get("_provider_attempts")
    assert len(calls) == 1


@pytest.mark.parametrize("refs", [[], ["https://example.test/cup.png"]])
async def test_grok_video_sends_exact_model_and_reference_contract(refs):
    def respond(request):
        assert request.url.path == "/v1/videos/generations"
        assert json.loads(request.content) == {
            "model": "grok-imagine-video-1.5", "prompt": "A rotating cup",
            "duration": 3, "resolution": "480p", "aspect_ratio": "16:9",
            **({"reference_images": [{"url": refs[0]}]} if refs else {}),
        }
        return httpx.Response(202, json={"request_id": "grok-request"})

    async with httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(respond)) as http:
        client = NeironychVideoClient("test-key", "https://provider.test", client=http)
        result = await client.create_video(
            model="grok-imagine-video-1.5",
            payload={"prompt": "A rotating cup", "duration": 3, "resolution": "480p",
                     "aspect_ratio": "16:9", "image_urls": refs},
            idempotency_key="contract-grok-test",
        )
    assert result == "grok-request"


@pytest.mark.parametrize("changes", [
    {"duration": 16}, {"duration": 3.5}, {"duration": True},
    {"resolution": "1080p", "image_urls": ["https://example.test/ref.png"]},
    {"image_urls": [f"https://example.test/{i}.png" for i in range(8)]},
    {"aspect_ratio": "auto"}, {"seed": 42},
    {"nsfw_checker": True},
])
async def test_grok_unsupported_settings_never_make_paid_request(changes):
    def forbidden(_request):
        raise AssertionError("No paid POST for unsupported Grok settings")

    async with httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(forbidden)) as http:
        client = NeironychVideoClient("test-key", "https://provider.test", client=http)
        with pytest.raises(NeironychProviderError) as caught:
            await client.create_video(model="grok-imagine-video-1.5",
                payload={"prompt": "A rotating cup", "duration": 3, **changes},
                idempotency_key="contract-grok-test")
    assert caught.value.local_validation


async def test_route_registry_expansion_preserves_existing_admin_opt_outs():
    # Snapshot of the prior complete registry, with deliberate admin choices.
    prior = {model: choices[0] for model, choices in route_options().items() if model != "grok-video-1.5"}
    prior["nano-banana-pro"] = ["kie"]
    prior["seedream-5-pro-t2i"] = ["kie", "nexus"]
    for model in ("nano-banana-2", "nano-banana-2-lite", "gpt-image-2-t2i", "gpt-image-2-i2i"):
        prior[model] = ["nexus", "kie"]
    prior["seedance-2.5"] = ["nexus", "neironych"]

    class Session:
        async def get(self, *_args, **_kwargs):
            return SimpleNamespace(value={"revision": 6, "routes": prior})

    config = await configured_routes(Session())
    assert config["revision"] == 6
    assert config["routes"]["nano-banana-pro"] == ["kie"]
    assert config["routes"]["seedream-5-pro-t2i"] == ["kie", "nexus"]
    for model in ("nano-banana-2", "nano-banana-2-lite", "gpt-image-2-t2i", "gpt-image-2-i2i"):
        assert config["routes"][model] == ["nexus", "neironych", "kie"]
    assert config["routes"]["seedance-2.5"] == ["nexus", "neironych"]
    assert config["routes"]["grok-video-1.5"] == ["kie", "neironych"]


async def test_new_registry_keeps_explicit_admin_opt_out_after_migration():
    routes = {model: choices[0] for model, choices in route_options().items()}
    routes["nano-banana-2"] = ["nexus", "kie"]
    routes["nano-banana-2-lite"] = ["kie"]

    class Session:
        async def get(self, *_args, **_kwargs):
            return SimpleNamespace(value={"revision": 8, "routes": routes})

    config = await configured_routes(Session())
    assert config["routes"]["nano-banana-2"] == ["nexus", "kie"]
    assert config["routes"]["nano-banana-2-lite"] == ["kie"]


@pytest.mark.parametrize("model,inputs", [
    ("nano-banana-2", {"aspect_ratio": "auto"}),
    ("nano-banana-2-lite", {"aspect_ratio": "16:9", "resolution": "4K"}),
    ("grok-video-1.5", {"duration": 16}),
])
async def test_service_skips_only_unsupported_capability_before_post(monkeypatch, model, inputs):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("No provider client for unsupported input")

    monkeypatch.setattr("app.services.neironych_generation_provider.NeironychImageClient", forbidden)
    monkeypatch.setattr("app.services.neironych_generation_provider.NeironychVideoClient", forbidden)
    gid = await new_generation(model, **inputs)
    async with SessionFactory() as session:
        row = await Service.submit(session, gid)
        assert row.provider == "kie" and row.status == "retry"
        assert SNAPSHOT_KEY not in row.parameters


@pytest.mark.parametrize("model", ["nano-banana-2", "nano-banana-2-lite", "gpt-image-2-t2i", "gpt-image-2-i2i"])
async def test_new_image_unknown_outcome_never_reposts_or_falls_back(monkeypatch, model):
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("Lost response", request=request)

    async with httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(timeout)) as http:
        client = NeironychImageClient("test-key", "https://provider.test", client=http)
        monkeypatch.setattr("app.services.neironych_generation_provider.NeironychImageClient", lambda *_: client)
        gid = await new_generation(model, aspect_ratio="1:1")
        async with SessionFactory() as session:
            row = await Service.submit(session, gid)
            assert row.provider == "neironych" and row.status == "submitting"
            assert row.parameters["_submission_uncertain"]
        async with SessionFactory() as session:
            await Service.submit(session, gid)
    assert len(calls) == 1


async def test_image_edit_url_result_is_downloaded_without_provider_credentials(monkeypatch):
    original_client = httpx.AsyncClient
    content = b"synthetic-image-result"

    def response(request):
        if request.url.host == "provider.test":
            assert request.headers["Authorization"] == "Bearer secret-test-key"
            return httpx.Response(200, json={"data": [{"url": "https://cdn.test/result.png?signature=private"}]})
        assert request.url.host == "cdn.test"
        assert "Authorization" not in request.headers
        assert "Idempotency-Key" not in request.headers
        return httpx.Response(200, headers={"Content-Type": "image/png"}, content=content)

    transport = httpx.MockTransport(response)
    async def public_url(_url):
        pass  # DNS/redirect validation has dedicated MediaIngestService coverage.

    monkeypatch.setattr("app.services.media_assets.MediaIngestService._validate_public_https_url", public_url)
    async with original_client(base_url="https://provider.test", transport=transport) as http:
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))
        client = NeironychImageClient("secret-test-key", "https://provider.test", client=http)
        result = await client.create_image(model="gpt-image-2", prompt="Change blue to green",
            aspect_ratio="1:1", resolution="", image_urls=["https://example.test/ref.png"],
            idempotency_key="contract-url-test")
    assert result.content == content


async def test_image_url_result_cannot_fetch_internal_host():
    def response(_request):
        return httpx.Response(200, json={"data": [{"url": "https://127.0.0.1/private.png"}]})

    async with httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(response)) as http:
        client = NeironychImageClient("test-key", "https://provider.test", client=http)
        with pytest.raises(NeironychProviderError) as caught:
            await client.create_image(model="gpt-image-2", prompt="A cup", aspect_ratio="1:1",
                resolution="", image_urls=[], idempotency_key="contract-url-test")
    assert caught.value.error_code == "provider_response_invalid"


async def test_interrupted_grok_worker_replays_frozen_body_and_original_key(monkeypatch):
    gid = await new_generation("grok-video-1.5", duration=2, resolution="480p")
    async with SessionFactory() as session:
        row = await session.get(Generation, gid)
        await Service._freeze_new_submission(session, row)
        original = row.parameters[SNAPSHOT_KEY]
        row.status = "submitting"  # Worker died after POST, before binding accepted ID.
        await session.commit()

    claim = ClaimedGeneration(outbox_id=uuid.uuid4(), generation_id=gid, attempts=2)
    monkeypatch.setattr(GenerationOutboxService, "claim", AsyncMock(return_value=claim))
    monkeypatch.setattr(GenerationOutboxService, "release", AsyncMock())
    monkeypatch.setattr(AbuseProtectionService, "provider_submission_gate", AsyncMock())
    monkeypatch.setattr(AbuseProtectionService, "record_provider_success", AsyncMock())
    calls = []
    upstream_id = "original-grok-" + str(gid)

    def response(request):
        assert request.content.decode() == original["body_json"]
        assert request.headers["Idempotency-Key"] == original["idempotency_key"]
        calls.append(request)
        return httpx.Response(202, json={"request_id": upstream_id})

    async with httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(response)) as http:
        client = NeironychVideoClient("test-key", "https://provider.test", client=http)
        monkeypatch.setattr("app.services.neironych_generation_provider.NeironychVideoClient", lambda *_: client)
        assert await GenerationWorkerService.process_one(None)
    async with SessionFactory() as session:
        row = await session.get(Generation, gid)
        assert row.status == "generating" and row.external_id == upstream_id
        assert not row.parameters.get("_submission_uncertain")
    assert len(calls) == 1


@pytest.mark.parametrize("code", [401, 402, 404, 429])
async def test_grok_kie_availability_failure_dispatches_neironych_with_owned_reference(monkeypatch, code):
    class UnavailableKie:
        def __init__(self, *_args):
            pass
        async def create_task(self, **_kwargs):
            raise KieProviderError("Kie account unavailable", code=code)
        async def aclose(self):
            pass

    monkeypatch.setattr("app.services.generation_provider.KieClient", UnavailableKie)
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.test")
    # Kie media transport is unrelated to this no-task response; don't upload a reference.
    async def identity(data):
        return data
    monkeypatch.setattr("app.services.generation_provider.ProviderMediaTransport.prepare", identity)
    gid = await new_generation("grok-video-1.5", duration=2, resolution="480p",
                               image_urls=["/uploads/refs/synthetic.png"], nsfw_checker=False)
    async with SessionFactory() as session:
        row = await session.get(Generation, gid)
        row.provider = "kie"
        row.parameters = {**row.parameters, "_provider_route": ["kie", "neironych"]}
        await session.commit()
        row = await GenerationProviderService.submit_kie(session, gid)
        assert row.provider == "neironych" and row.status == "retry"

    def response(request):
        body = json.loads(request.content)
        assert body["model"] == "grok-imagine-video-1.5"
        assert body["reference_images"] == [{"url": "https://roxy.test/uploads/refs/synthetic.png"}]
        assert "nsfw_checker" not in body
        assert request.headers["Idempotency-Key"] == f"generation:{gid}:provider:1"
        return httpx.Response(202, json={"request_id": "fallback-grok-" + str(gid)})

    async with httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(response)) as http:
        client = NeironychVideoClient("test-key", "https://provider.test", client=http)
        monkeypatch.setattr("app.services.neironych_generation_provider.NeironychVideoClient", lambda *_: client)
        async with SessionFactory() as session:
            row = await Service.submit(session, gid)
            assert row.status == "generating" and row.external_id == "fallback-grok-" + str(gid)
            assert row.parameters["_provider_attempts"][0]["provider"] == "kie"
