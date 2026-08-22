from __future__ import annotations

import pytest

from app.services.generations import GenerationService


@pytest.mark.asyncio
async def test_auto_routing_strips_fields_unknown_to_resolved_provider_spec() -> None:
    spec, clean, _cost, _seconds, _unit = await GenerationService.prepare_request(
        object(),
        model_id="nano-banana",
        prompt="edit the portrait",
        parameters={
            "image_urls": ["https://example.com/ref.png"],
            "aspect_ratio": "1:1",
            "output_format": "png",
            # A stale setting from another image model must never reach Kie after
            # automatic routing to Nano Banana Edit.
            "resolution": "4K",
            "stale_provider_option": "legacy",
        },
    )

    assert spec.id == "nano-banana-edit"
    assert clean["prompt"] == "edit the portrait"
    assert clean["image_urls"] == ["https://example.com/ref.png"]
    assert clean["aspect_ratio"] == "1:1"
    assert clean["output_format"] == "png"
    assert "resolution" not in clean
    assert "stale_provider_option" not in clean
    assert set(clean) <= set(spec.known_fields)


@pytest.mark.asyncio
async def test_direct_generation_also_freezes_only_declared_fields() -> None:
    spec, clean, _cost, _seconds, _unit = await GenerationService.prepare_request(
        object(),
        model_id="gpt-image-2-t2i",
        prompt="studio portrait",
        parameters={"resolution": "2K", "obsolete_option": True},
    )

    assert spec.id == "gpt-image-2-t2i"
    assert clean["resolution"] == "2K"
    assert "obsolete_option" not in clean
    assert set(clean) <= set(spec.known_fields)
