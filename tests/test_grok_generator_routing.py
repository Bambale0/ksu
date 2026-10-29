from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import httpx

from app.db.models import User, Wallet
from app.db.session import SessionFactory
from app.services.generations import GenerationService
from app.providers.neironych_video import NeironychVideoClient
from app.services.neironych_generation_provider import NeironychGenerationProviderService
from app.services.generation_provider import GenerationProviderService
from app.services.generation_provider_routing import configured_routes, route_options
from app.services.generation_worker import GenerationWorkerService
from app.core.config import settings


class WakeRedis:
    async def eval(self, *_args, **_kwargs):
        return [1, 60]

    async def rpush(self, *_args, **_kwargs):
        return 1


async def admit(session, model, **changes):
    user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Grok route regression")
    session.add(user)
    await session.flush()
    session.add(Wallet(user_id=user.id, balance=Decimal("10000")))
    await session.commit()
    inputs = {"duration": 6, "mode": "normal", "resolution": "480p", "aspect_ratio": "16:9"}
    if model == "grok-video-i2v":
        inputs["image_urls"] = ["https://example.test/first-frame.png"]
    inputs.update(changes)
    return await GenerationService.create(
        session, WakeRedis(), user_id=user.id, model_id=model,
        prompt="A rotating ceramic cup", parameters=inputs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["grok-video-t2v", "grok-video-i2v"])
async def test_ordinary_grok_admission_snapshots_neironych_primary(model):
    async with SessionFactory() as session:
        generation = await admit(session, model)
        assert generation.provider == "neironych"
        assert generation.parameters["_provider_route"] == ["neironych", "kie"]
        assert generation.parameters["_model_id"] == model
        assert generation.parameters["mode"] == "normal"
        assert generation.cost_rox == Decimal("60.00" if model == "grok-video-t2v" else "90.00")


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["grok-video-t2v", "grok-video-i2v"])
@pytest.mark.parametrize("resolution", ["480p", "1080p"])
async def test_normal_grok_reaches_neironych_and_keeps_image_as_first_frame(monkeypatch, model, resolution):
    requests = []
    upstream_id = str(uuid.uuid4())

    def respond(request):
        requests.append(request)
        expected = {
            "model": "grok-imagine-video-1.5", "prompt": "A rotating ceramic cup",
            "duration": 6, "resolution": resolution, "aspect_ratio": "16:9",
        }
        if model == "grok-video-i2v":
            expected["image"] = {"url": "https://roxy.test/uploads/refs/first.png"}
        assert json.loads(request.content) == expected
        return httpx.Response(202, json={"request_id": upstream_id})

    async with httpx.AsyncClient(
        base_url="https://provider.test", transport=httpx.MockTransport(respond),
    ) as http:
        client = NeironychVideoClient("test-key", "https://provider.test", client=http)
        monkeypatch.setattr(
            "app.services.neironych_generation_provider.NeironychVideoClient", lambda *_: client,
        )
        monkeypatch.setattr(settings, "public_base_url", "https://roxy.test")
        async with SessionFactory() as session:
            changes = {"resolution": resolution}
            if model == "grok-video-i2v":
                changes["image_urls"] = ["/uploads/refs/first.png"]
            generation = await admit(session, model, **changes)
            row = await NeironychGenerationProviderService.submit(session, generation.id)
            assert row.provider == "neironych"
            assert row.status == "generating"
            assert row.external_id == upstream_id
            assert row.parameters["mode"] == "normal"
            again = await NeironychGenerationProviderService.submit(session, row.id)
            assert again.external_id == upstream_id
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["grok-video-t2v", "grok-video-i2v"])
@pytest.mark.parametrize("status", [402, 503])
async def test_ordinary_grok_fallback_requires_a_definite_no_task_response(monkeypatch, model, status):
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
        async with SessionFactory() as session:
            generation = await admit(session, model)
            row = await NeironychGenerationProviderService.submit(session, generation.id)
            assert row.provider == ("kie" if status == 402 else "neironych")
            assert row.status == "retry"
            assert row.parameters["mode"] == "normal"
            assert row.parameters["_provider_route_index"] == (1 if status == 402 else 0)
            if status == 503:
                assert row.parameters["_submission_uncertain"]
            else:
                # Exhaustion of the overall route restores exactly the original
                # debit, including repeated terminal handling.
                await GenerationProviderService.fail_and_refund(session, row.id, "Synthetic Kie failure")
                await GenerationProviderService.fail_and_refund(session, row.id, "Duplicate failure")
                wallet = await session.get(Wallet, row.user_id)
                assert wallet.balance == Decimal("10000.00")
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("model,changes", [
    ("grok-video-t2v", {"duration": 16}), ("grok-video-i2v", {"duration": 16}),
    ("grok-video-t2v", {"mode": "fun"}), ("grok-video-i2v", {"mode": "fun"}),
    ("grok-video-t2v", {"mode": "spicy"}),
])
async def test_unsupported_neironych_capability_preserves_kie_input_without_paid_post(
    monkeypatch, model, changes,
):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Unsupported input must fall back before a paid provider request")

    monkeypatch.setattr(
        "app.services.neironych_generation_provider.NeironychVideoClient", forbidden,
    )
    async with SessionFactory() as session:
        generation = await admit(session, model, **changes)
        row = await NeironychGenerationProviderService.submit(session, generation.id)
        assert row.provider == "kie" and row.status == "retry"
        for key, value in changes.items():
            assert row.parameters[key] == value
        assert row.parameters["_provider_attempts"][0]["provider"] == "neironych"


@pytest.mark.asyncio
async def test_new_grok_routes_merge_without_resetting_existing_admin_choices():
    prior = {model: choices[0] for model, choices in route_options().items()
             if model not in {"grok-video-t2v", "grok-video-i2v"}}
    prior["grok-video-1.5"] = ["neironych", "kie"]
    prior["seedance-2.5"] = ["nexus", "neironych"]
    prior["nano-banana-pro"] = ["kie"]

    class Session:
        async def get(self, *_args, **_kwargs):
            return SimpleNamespace(value={"revision": 5, "routes": prior})

    config = await configured_routes(Session())
    assert config["revision"] == 5
    assert {key: config["routes"][key] for key in prior} == prior
    assert config["routes"]["grok-video-t2v"] == ["neironych", "kie"]
    assert config["routes"]["grok-video-i2v"] == ["neironych", "kie"]
    prior.update({"grok-video-t2v": ["kie"], "grok-video-i2v": ["kie"]})
    assert (await configured_routes(Session()))["routes"] == prior


@pytest.mark.parametrize("external_id", [None, "legacy-accepted-task"])
def test_existing_unsnapshotted_grok_jobs_remain_bound_to_kie(external_id):
    row = SimpleNamespace(provider="kie", external_id=external_id,
                          parameters={"_model_id": "grok-video-i2v"})
    assert GenerationWorkerService._provider_name(row) == "kie"
