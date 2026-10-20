from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.db.models import Generation, User, Wallet
from app.db.session import SessionFactory
from app.providers.kie import KieClient, KieProviderError
from app.services.generation_provider import GenerationProviderService
from app.services.generation_provider_routing import route_options, validate_routes
from app.services.model_catalog import ModelCatalog
from app.services.nexus_generation_provider import NexusGenerationProviderService
from app.services.wallet import WalletService


@pytest.mark.parametrize("model", ["seedream-5-pro-t2i", "seedream-5-pro-i2i"])
def test_seedream_accepts_kie_primary_with_nexus_fallback(model):
    routes = {key: choices[0] for key, choices in route_options().items()}
    routes[model] = ["kie", "nexus"]
    assert validate_routes(routes)[model] == ["kie", "nexus"]
    assert ["nexus", "kie"] in route_options()[model]
    assert ["kie"] in route_options()[model]


def test_other_models_do_not_gain_reverse_routes():
    routes = {key: choices[0] for key, choices in route_options().items()}
    routes["nano-banana-2"] = ["kie", "nexus"]
    with pytest.raises(ValueError):
        validate_routes(routes)


async def make_job(session, model="seedream-5-pro-t2i"):
    user = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Seedream route test")
    session.add(user)
    await session.flush()
    await WalletService.ensure_wallet(session, user.id)
    await WalletService.credit(session, user_id=user.id, amount=Decimal("100"),
                               kind="test_credit", idempotency_key=str(uuid.uuid4()))
    params = {"_model_id": model, "_provider_route": ["kie", "nexus"],
              "_provider_route_index": 0, "aspect_ratio": "1:1", "quality": "basic",
              "output_format": "png"}
    if model.endswith("i2i"):
        params["image_urls"] = ["https://example.com/reference.png"]
    _, clean, *_ = ModelCatalog.prepare(model, params | {"prompt": "A blue ceramic cup"})
    params.update(clean)
    generation = Generation(user_id=user.id, provider="kie", kind="text_to_image",
                            status="queued", prompt="A blue ceramic cup", cost_rox=Decimal("20"),
                            parameters=params)
    session.add(generation)
    await session.flush()
    await WalletService.debit(session, user_id=user.id, amount=Decimal("20"),
                              kind="generation", idempotency_key=f"generation:{generation.id}")
    await session.commit()
    return generation


def mock_kie(monkeypatch, handler):
    def client(*_args, **_kwargs):
        instance = KieClient.__new__(KieClient)
        instance._client = httpx.AsyncClient(base_url="https://kie.example",
                                            transport=httpx.MockTransport(handler))
        return instance
    monkeypatch.setattr("app.services.generation_provider.KieClient", client)


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["seedream-5-pro-t2i", "seedream-5-pro-i2i"])
@pytest.mark.parametrize("code,envelope", [(401, False), (402, False), (404, False),
                                          (429, False), (402, True), (429, True)])
async def test_definite_kie_rejection_schedules_nexus_without_refund(monkeypatch, model, code, envelope):
    nexus_calls = []
    task_id = f"nexus-{uuid.uuid4()}"

    class NexusClient:
        def __init__(self, *_args):
            pass

        async def create_generation(self, *, params, idempotency_key):
            assert params["model_name"] == "seedream-5.0-pro"
            nexus_calls.append(idempotency_key)
            return task_id

        async def aclose(self):
            pass

    monkeypatch.setattr("app.services.nexus_generation_provider.NexusClient", NexusClient)
    def handler(request):
        payload = json.loads(request.content)
        assert payload["input"]["nsfw_checker"] is False
        assert payload["model"].startswith("seedream/5-pro-")
        return httpx.Response(200 if envelope else code,
                              json={"code": code, "msg": "availability rejection"})
    mock_kie(monkeypatch, handler)
    async with SessionFactory() as session:
        generation = await make_job(session, model)
        result = await GenerationProviderService.submit_kie(session, generation.id)
        assert result.provider == "nexus" and result.status == "retry"
        assert result.external_id is None
        assert result.parameters["_provider_route_index"] == 1
        attempt = result.parameters["_provider_attempts"][0]
        assert attempt["provider"] == "kie"
        assert attempt["reason"] == f"Kie unavailable HTTP/code {code}"
        wallet = await session.get(Wallet, generation.user_id)
        assert wallet.balance == Decimal("80")
        result = await NexusGenerationProviderService.submit(session, generation.id)
        assert result.provider == "nexus" and result.external_id == task_id
        await NexusGenerationProviderService.submit(session, generation.id)
        assert nexus_calls == [f"generation:{generation.id}"]
        await session.refresh(wallet)
        assert wallet.balance == Decimal("80")
        await GenerationProviderService.fail_and_refund(session, generation.id, "final")
        await GenerationProviderService.fail_and_refund(session, generation.id, "replay")
        await session.refresh(wallet)
        assert wallet.balance == Decimal("100")


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["timeout", "server", "malformed", "policy", "validation", "task_id", "http_task_id", "http_malformed"])
async def test_kie_unsafe_outcomes_do_not_start_nexus(monkeypatch, outcome):
    def handler(request):
        if outcome == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if outcome == "malformed":
            return httpx.Response(200, text="invalid json")
        if outcome == "task_id":
            return httpx.Response(200, json={"code": 429, "data": {"taskId": "maybe-accepted"}})
        if outcome == "http_task_id":
            return httpx.Response(429, json={"code": 429, "data": {"taskId": "maybe-accepted"}})
        if outcome == "http_malformed":
            return httpx.Response(429, text="invalid json")
        return httpx.Response({"server": 503, "policy": 403, "validation": 422}[outcome],
                              json={"code": 500, "msg": "rejected"})
    mock_kie(monkeypatch, handler)
    async with SessionFactory() as session:
        generation = await make_job(session)
        with pytest.raises((httpx.HTTPError, json.JSONDecodeError, KieProviderError)):
            await GenerationProviderService.submit_kie(session, generation.id)
        await session.refresh(generation)
        assert generation.provider == "kie"
        assert generation.parameters["_provider_route_index"] == 0
        wallet = await session.get(Wallet, generation.user_id)
        if outcome in {"timeout", "server", "malformed", "task_id", "http_task_id", "http_malformed"}:
            assert generation.parameters["_submission_uncertain"] is True
            assert wallet.balance == Decimal("80")
        else:
            assert generation.status == "failed" and wallet.balance == Decimal("100")


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["accepted", "uncertain", "switched", "failed"])
async def test_late_kie_availability_error_preserves_newer_outcome(monkeypatch, state):
    accepted_task = f"accepted-{uuid.uuid4()}"
    async with SessionFactory() as session:
        generation = await make_job(session)
        async def handler(request):
            async with SessionFactory() as other:
                row = await other.get(Generation, generation.id)
                row.status = "generating"
                if state == "accepted":
                    row.external_id = accepted_task
                elif state == "uncertain":
                    row.status = "submitting"
                    row.parameters = row.parameters | {"_submission_uncertain": True,
                                                       "_submission_uncertain_at": datetime.now(UTC).isoformat()}
                elif state == "switched":
                    row.provider = "nexus"
                    row.parameters = row.parameters | {"_provider_route_index": 1}
                else:
                    await GenerationProviderService.fail_and_refund(other, row.id, "already failed")
                await other.commit()
            return httpx.Response(429, json={"code": 429})
        mock_kie(monkeypatch, handler)
        result = await GenerationProviderService.submit_kie(session, generation.id)
        assert not result.parameters.get("_provider_attempts")
        if state == "accepted":
            assert result.external_id == accepted_task and result.status == "generating"
        elif state == "uncertain":
            assert result.parameters["_submission_uncertain"] and result.status == "submitting"
        elif state == "switched":
            assert result.provider == "nexus" and result.parameters["_provider_route_index"] == 1
        else:
            assert result.status == "failed"

