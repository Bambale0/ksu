from decimal import Decimal

import pytest

from app.api.v1.generations import generation_models
from app.core.config import settings
from app.db.session import SessionFactory
from app.services.generations import GenerationService


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
