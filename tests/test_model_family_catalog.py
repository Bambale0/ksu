from __future__ import annotations

from decimal import Decimal

from app.services.model_catalog import ModelCatalog
from app.services.model_family_catalog import build_model_families
from app.services.model_presentation import presentation_for
from app.services.model_ui_contract import build_public_model_ui_schema
from app.services.trending_model_catalog import TRENDING_PUBLIC_MODEL_ORDER


def _public_models() -> list[dict[str, object]]:
    models: list[dict[str, object]] = []
    for item in ModelCatalog.list():
        model = dict(item)
        model["presentation"] = presentation_for(model)
        model["ui_schema"] = build_public_model_ui_schema(model)
        models.append(model)
    return models


def test_family_catalog_groups_current_tanya_product_layer() -> None:
    families = build_model_families(_public_models())
    ids = [item["family"] for item in families]
    assert ids[:9] == [
        "nano_banana",
        "seedream",
        "gpt_image",
        "kling",
        "seedance",
        "veo",
        "gemini",
        "grok",
        "wan",
    ]

    public_ids = {
        variant["id"]
        for family in families
        for variant in family["variants"]
    }
    assert public_ids < set(TRENDING_PUBLIC_MODEL_ORDER)
    assert "gpt-image-2-i2i" in public_ids
    assert "gpt-image-2-t2i" not in public_ids
    assert "seedream-5-pro-i2i" in public_ids
    assert "seedream-5-pro-t2i" not in public_ids


def test_auto_routed_variants_keep_customer_friendly_copy() -> None:
    families = {item["family"]: item for item in build_model_families(_public_models())}

    gpt = next(
        variant
        for variant in families["gpt_image"]["variants"]
        if variant["id"] == "gpt-image-2-i2i"
    )
    assert gpt["operation"] == "auto"
    assert gpt["auto_mode"] is True
    assert gpt["version"] == "GPT Image 2"
    assert gpt["description"] == "Сильное качество и точное следование промпту"
    assert "референс" not in gpt["description"].lower()
    assert "автоматически" not in gpt["description"].lower()

    seedream_ids = {variant["id"] for variant in families["seedream"]["variants"]}
    assert "seedream-5-pro-i2i" in seedream_ids
    assert "seedream-5-pro-t2i" not in seedream_ids


def test_nano_banana_variants_are_top_first_and_keep_variant_pricing() -> None:
    families = {item["family"]: item for item in build_model_families(_public_models())}
    variants = families["nano_banana"]["variants"]
    assert [variant["id"] for variant in variants] == [
        "nano-banana-pro",
        "nano-banana-2",
        "nano-banana-2-lite",
    ]
    assert [variant["version"] for variant in variants] == [
        "Nano Banana Pro",
        "Nano Banana 2",
        "Nano Banana 2 Lite",
    ]
    assert [variant["description"] for variant in variants] == [
        "Максимальное качество, лучше для финального результата",
        "Оптимальный баланс качества и скорости",
        "Быстрее и дешевле для черновиков",
    ]
    assert variants[0]["badge"] == "TOP"
    assert variants[0]["recommended"] is True
    assert [Decimal(str(variant["price_rox"])) for variant in variants] == [
        Decimal(str(ModelCatalog.get("nano-banana-pro").public_dict()["price_rox"])),
        Decimal(str(ModelCatalog.get("nano-banana-2").public_dict()["price_rox"])),
        Decimal(str(ModelCatalog.get("nano-banana-2-lite").public_dict()["price_rox"])),
    ]
    assert all(variant.get("ui_schema") for variant in variants)


def test_admin_free_variants_still_show_retail_price() -> None:
    model = ModelCatalog.get("gpt-image-2-i2i").public_dict()
    model["presentation"] = presentation_for(model)
    model["ui_schema"] = build_public_model_ui_schema(model)
    model["admin_free"] = True
    model["retail_price_rox"] = "180.00"
    model["price_rox"] = "0.00"
    model["price_credits"] = "0.00"
    model["price_rub"] = "0.00"

    families = build_model_families([model])
    variant = families[0]["variants"][0]

    assert families[0]["price_from_rox"] == "180.00"
    assert variant["price_rox"] == "180.00"
    assert variant["price_credits"] == "180.00"
    assert variant["effective_price_rox"] == "0.00"
    assert variant["admin_free"] is True
