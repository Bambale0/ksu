from __future__ import annotations

import pytest

from app.services.kie_image_contracts import KieImageContractError, normalize_kie_image_input
from app.services.model_catalog import ModelCatalog
from app.services.model_routing import resolve_model_request
from app.services.model_ui_contract import build_public_model_ui_schema


@pytest.mark.parametrize("model_id", ["gpt-image-2-t2i", "gpt-image-2-i2i"])
def test_gpt_image_2_exposes_current_resolution_enum(model_id: str) -> None:
    spec = ModelCatalog.get(model_id)
    assert "resolution" in spec.known_fields
    schema = build_public_model_ui_schema(spec.public_dict())
    field = next(item for item in schema["fields"] if item["name"] == "resolution")
    assert field["suggestions"] == ["1K", "2K", "4K"]
    assert schema["defaults"]["resolution"] == "1K"


def test_gpt_image_2_auto_routing_preserves_resolution() -> None:
    text = resolve_model_request(
        "gpt-image-2-t2i",
        {"prompt": "studio product shot", "aspect_ratio": "1:1", "resolution": "4K"},
    )
    assert text.model_id == "gpt-image-2-t2i"
    assert text.parameters["resolution"] == "4K"

    image = resolve_model_request(
        "gpt-image-2-t2i",
        {
            "prompt": "keep the product, change the background",
            "input_urls": ["https://cdn.example/product.png"],
            "aspect_ratio": "1:1",
            "resolution": "2K",
        },
    )
    assert image.model_id == "gpt-image-2-i2i"
    assert image.parameters["resolution"] == "2K"

    spec, clean, _cost, _seconds, _unit = ModelCatalog.prepare(image.model_id, image.parameters)
    payload = normalize_kie_image_input(spec.kie_model, clean)
    assert payload["resolution"] == "2K"
    assert payload["input_urls"] == ["https://cdn.example/product.png"]


def test_gpt_image_2_rejects_large_resolution_ratio_combinations_provider_does_not_support() -> None:
    with pytest.raises(KieImageContractError, match="does not support"):
        normalize_kie_image_input(
            "gpt-image-2-text-to-image",
            {"prompt": "x", "resolution": "4K", "aspect_ratio": "5:4"},
        )
