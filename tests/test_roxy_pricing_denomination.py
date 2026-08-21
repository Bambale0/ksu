import uuid
from decimal import Decimal

import pytest

from app.api.v1.generations import CreateGenerationRequest, generation_models, quote_generation
from app.core.config import settings
from app.db.session import SessionFactory
from app.services.billing_access import BillingAccessService, BillingDecision
from app.services.generations import GenerationService


class _AdminUser:
    id = uuid.uuid4()


@pytest.mark.asyncio
async def test_builtin_generation_price_is_redenominated_without_changing_rub_price() -> None:
    previous = settings.generation_pricing_json
    settings.generation_pricing_json = "{}"
    try:
        async with SessionFactory() as session:
            _spec, _params, cost, seconds, unit_price = await GenerationService.prepare_request(
                session,
                model_id="kling-3.0",
                prompt="city at night",
                parameters={"duration": 5},
            )
    finally:
        settings.generation_pricing_json = previous

    assert seconds == 5
    assert unit_price == Decimal("150.00")
    assert cost == Decimal("750.00")


@pytest.mark.asyncio
async def test_explicit_generation_price_override_is_already_public_rox() -> None:
    previous = settings.generation_pricing_json
    settings.generation_pricing_json = '{"kling-3.0":{"per_second":"72.50"}}'
    try:
        async with SessionFactory() as session:
            _spec, _params, cost, seconds, unit_price = await GenerationService.prepare_request(
                session,
                model_id="kling-3.0",
                prompt="city at night",
                parameters={"duration": 4},
            )
    finally:
        settings.generation_pricing_json = previous

    assert seconds == 4
    assert unit_price == Decimal("72.50")
    assert cost == Decimal("290.00")


@pytest.mark.asyncio
async def test_public_model_catalog_uses_same_public_rox_unit() -> None:
    previous = settings.generation_pricing_json
    settings.generation_pricing_json = "{}"
    try:
        payload = await generation_models(None, None)
    finally:
        settings.generation_pricing_json = previous

    model = next(item for item in payload["models"] if item["id"] == "gpt-image-2-t2i")
    assert model["price_rox"] == "180.00"
    assert model["price_credits"] == "180.00"
    assert model["price_rub"] == "180.00"
    assert payload["internal_credit_rub"] == "1.00"


@pytest.mark.asyncio
async def test_admin_model_catalog_still_exposes_retail_prices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def active_admin(_session: object, _user_id: uuid.UUID) -> bool:
        return True

    monkeypatch.setattr(BillingAccessService, "is_active_admin", active_admin)

    payload = await generation_models(_AdminUser(), None)

    model = next(item for item in payload["models"] if item["id"] == "gpt-image-2-t2i")
    family = next(item for item in payload["families"] if item["family"] == "gpt_image")
    variant = next(item for item in family["variants"] if item["id"] == "gpt-image-2-i2i")

    assert payload["admin_free"] is True
    assert model["admin_free"] is True
    assert Decimal(str(model["price_rox"])) > 0
    assert model["price_rox"] == model["retail_price_rox"]
    assert model["effective_price_rox"] == "0.00"
    assert Decimal(str(family["price_from_rox"])) > 0
    assert Decimal(str(variant["price_rox"])) > 0
    assert variant["price_rox"] == variant["retail_price_rox"]
    assert variant["effective_price_rox"] == "0.00"


@pytest.mark.asyncio
async def test_admin_quote_shows_retail_cost_but_keeps_effective_cost_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def admin_decision(
        _session: object,
        *,
        user_id: uuid.UUID,
        retail_cost: Decimal | str | int | float,
    ) -> BillingDecision:
        retail = Decimal(str(retail_cost)).quantize(Decimal("0.01"))
        return BillingDecision(retail_cost=retail, effective_cost=Decimal("0.00"), admin_free=True)

    monkeypatch.setattr(BillingAccessService, "decision", admin_decision)

    async with SessionFactory() as session:
        payload = await quote_generation(
            CreateGenerationRequest(
                model_id="gpt-image-2-t2i",
                prompt="city at night",
                parameters={},
            ),
            _AdminUser(),
            session,
        )

    assert payload["admin_free"] is True
    assert Decimal(str(payload["cost_rox"])) > 0
    assert payload["cost_rox"] == payload["retail_cost_rox"]
    assert payload["effective_cost_rox"] == "0.00"
