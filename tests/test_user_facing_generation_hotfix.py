from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import _generation_pricing_with_defaults, settings
from app.db.session import SessionFactory
from app.services.generation_provider import GenerationProviderService
from app.services.generations import GenerationService


def test_generation_pricing_env_cannot_erase_canonical_roxy_defaults() -> None:
    empty = json.loads(_generation_pricing_with_defaults("{}"))
    assert empty["nano-banana-2"]["flat"] == 25
    assert empty["gpt-image-2-t2i"]["flat"] == 20

    partial = json.loads(
        _generation_pricing_with_defaults('{"gpt-image-2-i2i":{"flat":31}}')
    )
    assert partial["gpt-image-2-i2i"]["flat"] == 31
    assert partial["nano-banana-2"]["flat"] == 25


@pytest.mark.asyncio
async def test_reference_switches_public_product_contract_before_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reference must affect the real server contract, not only the UI preview."""

    monkeypatch.setattr(
        settings,
        "generation_pricing_json",
        json.dumps(
            {
                "gpt-image-2-t2i": {"flat": 20},
                "gpt-image-2-i2i": {"flat": 31},
            }
        ),
    )

    async with SessionFactory() as session:
        text_spec, text_clean, text_cost, _seconds, _unit = await GenerationService.prepare_request(
            session,
            model_id="gpt-image-2-i2i",
            prompt="Editorial portrait",
            parameters={"aspect_ratio": "1:1", "resolution": "1K"},
        )
        assert text_spec.id == "gpt-image-2-t2i"
        assert text_cost == 20
        assert "input_urls" not in text_clean

        reference_url = "https://cdn.example.invalid/reference.png"
        ref_spec, ref_clean, ref_cost, _seconds, _unit = await GenerationService.prepare_request(
            session,
            model_id="gpt-image-2-i2i",
            prompt="Keep the person from the reference",
            parameters={
                "input_urls": [reference_url],
                "aspect_ratio": "1:1",
                "resolution": "1K",
            },
        )
        assert ref_spec.id == "gpt-image-2-i2i"
        assert ref_cost == 31
        assert ref_clean["input_urls"] == [reference_url]

        provider_input = GenerationProviderService._input_for(
            SimpleNamespace(
                action_type="generation",
                parameters={**ref_clean, "_model_id": ref_spec.id},
                prompt="Keep the person from the reference",
                input_url=None,
            )
        )
        assert provider_input["input_urls"] == [reference_url]


@pytest.mark.asyncio
async def test_nano_banana_2_keeps_all_selected_references_in_provider_payload() -> None:
    async with SessionFactory() as session:
        references = [
            "https://cdn.example.invalid/ref-a.png",
            "https://cdn.example.invalid/ref-b.png",
        ]
        spec, clean, _cost, _seconds, _unit = await GenerationService.prepare_request(
            session,
            model_id="nano-banana-2",
            prompt="Use both references",
            parameters={
                "image_input": references,
                "aspect_ratio": "auto",
                "resolution": "1K",
                "output_format": "png",
            },
        )
        assert clean["image_input"] == references

        provider_input = GenerationProviderService._input_for(
            SimpleNamespace(
                action_type="generation",
                parameters={**clean, "_model_id": spec.id},
                prompt="Use both references",
                input_url=None,
            )
        )
        assert provider_input["image_input"] == references


def test_generation_price_and_publication_frontend_contracts() -> None:
    root = Path(__file__).resolve().parents[1]
    api_source = (root / "frontend" / "mini-app" / "lib" / "api.ts").read_text(encoding="utf-8")
    privacy_source = (root / "frontend" / "mini-app" / "public" / "publish-privacy.js").read_text(encoding="utf-8")
    price_source = (root / "frontend" / "mini-app" / "public" / "rox-price-only.js").read_text(encoding="utf-8")
    layout_source = (root / "frontend" / "mini-app" / "app" / "layout.tsx").read_text(encoding="utf-8")

    assert "references_visible: Boolean(normalized.referencesVisible)" in api_source
    assert "body.references_visible = false" not in privacy_source
    assert "referenceRow.remove()" not in privacy_source
    assert 'includes("₽")' in price_source
    assert "node.hidden = isRubleEquivalent" in price_source
    assert '/mini-app/rox-price-only.js' in layout_source
