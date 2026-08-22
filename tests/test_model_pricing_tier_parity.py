from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.session import SessionFactory
from app.services.generations import GenerationService
from app.services.model_catalog import ModelCatalog


@pytest.mark.asyncio
async def test_generation_service_and_catalog_share_resolution_over_mode_precedence() -> None:
    previous = settings.generation_pricing_json
    settings.generation_pricing_json = (
        '{"grok-video-t2v":{"per_second":10,'
        '"by_mode":{"normal":12},'
        '"by_resolution":{"1080p":20}}}'
    )
    params = {
        "prompt": "cinematic city reveal",
        "mode": "normal",
        "resolution": "1080p",
        "aspect_ratio": "16:9",
        "duration": 6,
        "nsfw_checker": True,
    }
    try:
        _spec, _clean, catalog_cost, catalog_seconds, catalog_unit = ModelCatalog.prepare(
            "grok-video-t2v", params
        )
        async with SessionFactory() as session:
            _spec, _clean, generation_cost, generation_seconds, generation_unit = (
                await GenerationService.prepare_request(
                    session,
                    model_id="grok-video-t2v",
                    prompt=params["prompt"],
                    parameters=params,
                )
            )
    finally:
        settings.generation_pricing_json = previous

    assert catalog_seconds == generation_seconds == 6
    assert catalog_unit == generation_unit == Decimal("20")
    assert catalog_cost == generation_cost == Decimal("120.00")
