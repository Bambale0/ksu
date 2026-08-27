import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.pricing_runtime_sync import _PRICE_SENSITIVE_REQUESTS
from app.services.admin_pricing import (
    MUSIC_MODEL_ID,
    TariffValidationError,
    _activate_generation_pricing,
    validate_tariff_payload,
)
from app.services.model_catalog import ModelCatalog
from app.services.model_family_catalog import build_model_families
from app.services.music_generation import MusicGenerationService


def test_admin_generation_pricing_accepts_suno_with_same_flat_contract() -> None:
    payload = validate_tariff_payload(
        {"generation_pricing": {MUSIC_MODEL_ID: {"flat": 29}}}
    )
    assert payload["generation_pricing"][MUSIC_MODEL_ID]["flat"] == 29

    with pytest.raises(TariffValidationError, match="requires base flat"):
        validate_tariff_payload(
            {"generation_pricing": {MUSIC_MODEL_ID: {"per_second": 29}}}
        )


def test_published_admin_tariff_drives_regular_and_music_model_picker_prices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "generation_pricing_json", settings.generation_pricing_json)
    monkeypatch.setattr(settings, "music_generation_price_rox", settings.music_generation_price_rox)

    _activate_generation_pricing(
        {
            "generation_pricing": {
                "kling-3.0": {"per_second": 31},
                MUSIC_MODEL_ID: {"flat": 29},
            }
        }
    )

    overrides = json.loads(settings.generation_pricing_json)
    assert Decimal(str(overrides["kling-3.0"]["per_second"])) == Decimal("31")
    assert settings.music_generation_price_rox == Decimal("29")
    assert ModelCatalog.unit_price("kling-3.0") == Decimal("31")

    music_model = MusicGenerationService.public_model()
    assert music_model["price_rox"] == "29.00"
    _clean, music_price = MusicGenerationService.prepare({}, "cinematic synth track")
    assert music_price == Decimal("29.00")

    families = build_model_families(
        [ModelCatalog.get("kling-3.0").public_dict(), music_model]
    )
    by_family = {item["id"]: item for item in families}
    assert by_family["kling"]["price_from_rox"] == "31.00"
    assert by_family["kling"]["variants"][0]["price_rox"] == "31.00"
    assert by_family["suno"]["price_from_rox"] == "29.00"
    assert by_family["suno"]["variants"][0]["price_rox"] == "29.00"


def test_price_sensitive_customer_boundaries_force_runtime_tariff_sync() -> None:
    assert ("GET", "/api/v1/generations/models") in _PRICE_SENSITIVE_REQUESTS
    assert ("POST", "/api/v1/generations/quote") in _PRICE_SENSITIVE_REQUESTS
    assert ("POST", "/api/v1/generations") in _PRICE_SENSITIVE_REQUESTS

    main = Path("app/main.py").read_text(encoding="utf-8")
    assert "PricingRuntimeSyncMiddleware" in main
    assert "app.add_middleware(PricingRuntimeSyncMiddleware)" in main


def test_every_family_variant_uses_explicit_price_surface() -> None:
    source = Path("frontend/mini-app/components/roxy-app.tsx").read_text(encoding="utf-8")
    css = Path("frontend/mini-app/app/catalog.css").read_text(encoding="utf-8")

    assert "family.variants.map" in source
    assert "priceLabel(variant.price_rox)" in source
    assert ".variant-row > .price-pill" in css
    assert 'content: "Цена"' in css
    assert "font-size: 12px" in css
