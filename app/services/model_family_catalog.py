from __future__ import annotations

from decimal import Decimal
from typing import Any


FAMILY_ORDER: tuple[str, ...] = (
    "nano_banana",
    "seedream",
    "gpt_image",
    "kling",
    "seedance",
    "veo",
    "gemini",
    "grok",
    "wan",
    "suno",
)

FAMILY_TITLES = {
    "nano_banana": "Nano Banana",
    "seedream": "Seedream",
    "gpt_image": "GPT Image",
    "kling": "Kling",
    "seedance": "Seedance",
    "veo": "Veo",
    "gemini": "Gemini",
    "grok": "Grok",
    "wan": "Wan",
    "suno": "Suno",
}

FAMILY_ICONS = {
    "nano_banana": "banana",
    "seedream": "spark",
    "gpt_image": "image",
    "kling": "video",
    "seedance": "video",
    "veo": "video",
    "gemini": "spark",
    "grok": "spark",
    "wan": "image",
    "suno": "music",
}

GROUP_TO_FAMILY = {
    "nano-banana": "nano_banana",
    "seedream": "seedream",
    "gpt-image": "gpt_image",
    "kling-video": "kling",
    "kling-motion": "kling",
    "kling-avatar": "kling",
    "seedance": "seedance",
    "grok-video": "grok",
    "wan-image": "wan",
}

MODEL_TO_FAMILY = {
    "veo-3.1": "veo",
    "gemini-omni-video": "gemini",
    "grok-image-t2i": "grok",
    "grok-image-i2i": "grok",
    "grok-video-t2v": "grok",
    "grok-video-i2v": "grok",
    "grok-video-1.5": "grok",
    "wan-2.7-t2v": "wan",
    "wan-2.7-i2v": "wan",
    "wan-2.7-video-edit": "wan",
    "wan-2.7-r2v": "wan",
    "suno-v5.5": "suno",
}

VARIANT_META = {
    "nano-banana-pro": {"badge": "TOP", "recommended": True, "description": "Лучшее качество", "order": 0},
    "nano-banana-2": {"badge": None, "recommended": False, "description": "Оптимальный баланс", "order": 1},
    "nano-banana-2-lite": {"badge": None, "recommended": False, "description": "Быстрые генерации", "order": 2},
}


def _family_id(model: dict[str, Any]) -> str:
    model_id = str(model.get("id") or "")
    presentation = model.get("presentation") if isinstance(model.get("presentation"), dict) else {}
    group = str(presentation.get("family_group") or "")
    if group in GROUP_TO_FAMILY:
        return GROUP_TO_FAMILY[group]
    if model_id in MODEL_TO_FAMILY:
        return MODEL_TO_FAMILY[model_id]
    title = str(presentation.get("family_title") or model.get("family") or model_id).lower()
    for family_id in FAMILY_ORDER:
        if family_id.replace("_", " ") in title.replace("-", " "):
            return family_id
    return model_id.replace("-", "_")


def _price_value(model: dict[str, Any]) -> Decimal:
    raw = model.get("price_rox") or model.get("price_credits") or "0"
    return Decimal(str(raw))


def _variant(model: dict[str, Any]) -> dict[str, Any]:
    model_id = str(model.get("id") or "")
    presentation = model.get("presentation") if isinstance(model.get("presentation"), dict) else {}
    meta = VARIANT_META.get(model_id, {})
    return {
        "id": model_id,
        "title": str(model.get("title") or model_id),
        "version": str(presentation.get("version_label") or model.get("title") or model_id),
        "operation": str(model.get("operation") or ""),
        "media_type": str(model.get("media_type") or ""),
        "price_rox": model.get("price_rox"),
        "price_credits": model.get("price_credits"),
        "price_rub": model.get("price_rub"),
        "retail_price_rox": model.get("retail_price_rox"),
        "badge": meta.get("badge"),
        "recommended": bool(meta.get("recommended", False)),
        "description": meta.get("description") or str(presentation.get("product_title") or model.get("title") or model_id),
        "ui_schema": model.get("ui_schema"),
        "order": int(meta.get("order", 1000)),
    }


def build_model_families(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for model in models:
        grouped.setdefault(_family_id(model), []).append(_variant(model))

    families: list[dict[str, Any]] = []
    for family_id, variants in grouped.items():
        variants.sort(
            key=lambda item: (
                not item["recommended"],
                item["order"],
                _price_value(item),
                str(item["title"]),
            )
        )
        prices = [_price_value(item) for item in variants if item.get("price_rox") is not None]
        families.append(
            {
                "family": family_id,
                "id": family_id,
                "title": FAMILY_TITLES.get(family_id, variants[0]["title"]),
                "icon": FAMILY_ICONS.get(family_id, "spark"),
                "media_types": sorted({str(item["media_type"]) for item in variants if item.get("media_type")}),
                "variant_count": len(variants),
                "price_from_rox": format(min(prices), ".2f") if prices else None,
                "variants": [
                    {key: value for key, value in item.items() if key != "order"}
                    for item in variants
                ],
            }
        )
    order = {family_id: index for index, family_id in enumerate(FAMILY_ORDER)}
    families.sort(key=lambda item: (order.get(str(item["family"]), 1000), str(item["title"])))
    return families
