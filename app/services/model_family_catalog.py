from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.services.model_routing import PUBLIC_REFERENCE_OPTIONAL_MODEL_IDS

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

# One short line per customer-visible product. These labels are deliberately
# about user outcomes, not provider modes: reference support is baseline and is
# not repeated on every card.
PRODUCT_DESCRIPTIONS = {
    "nano-banana": "Быстрые изображения для простых идей",
    "nano-banana-pro": "Максимальное качество, лучше для финального результата",
    "nano-banana-2": "Оптимальный баланс качества и скорости",
    "nano-banana-2-lite": "Быстрее и дешевле для черновиков",
    "seedream-3": "Стабильная генерация изображений",
    "seedream-4": "Фотореализм и аккуратное редактирование",
    "seedream-4.5": "Детальные изображения с хорошей стилизацией",
    "seedream-5-lite": "Быстрая генерация с хорошим качеством",
    "seedream-5-pro": "Премиум-качество для сложных сцен",
    "gpt-image-1.5": "Аккуратные иллюстрации и понятные правки",
    "gpt-image-2": "Сильное качество и точное следование промпту",
    "wan-2.7-image": "Универсальные изображения и быстрые правки",
    "wan-2.7-image-pro": "Больше деталей и выше качество картинки",
    "wan-2.7-video": "Универсальное видео по сценарию",
    "seedance-1.5-pro": "Надёжное видео с хорошей динамикой",
    "seedance-2.0": "Сбалансированное видео для большинства задач",
    "seedance-2.0-fast": "Быстрые видео, когда важна скорость",
    "seedance-2.0-mini": "Экономичный вариант для коротких тестов",
    "seedance-2.5": "Более сильная версия для детальных роликов",
    "kling-2.5-turbo-pro": "Кинематографичное видео в турбо-режиме",
    "kling-3.0": "Кинематографичное видео с гибкой сценой",
    "kling-motion-2.6": "Перенос движения с точным контролем",
    "kling-motion-3.0": "Продвинутый motion control для персонажей",
    "kling-avatar-standard": "Говорящий аватар для быстрых роликов",
    "kling-avatar-pro": "Говорящий аватар с лучшим качеством",
    "veo-3.1": "Премиум-видео с реалистичной динамикой",
    "gemini-omni-video": "Мультимодальное видео с медиа и персонажами",
    "grok-image": "Быстрые креативные изображения",
    "grok-video": "Динамичные ролики в стиле Grok",
    "grok-video-1.5": "Свежий preview для видео-экспериментов",
    "grok-video-upscale": "Улучшение качества готового видео",
    "grok-video-extend": "Продление готового видео",
    "suno-v5.5": "Музыка и песни по описанию",
}

VARIANT_META = {
    "nano-banana-pro": {
        "badge": "TOP",
        "recommended": True,
        "description": PRODUCT_DESCRIPTIONS["nano-banana-pro"],
        "order": 0,
    },
    "nano-banana-2": {
        "badge": "2",
        "recommended": False,
        "description": PRODUCT_DESCRIPTIONS["nano-banana-2"],
        "order": 1,
    },
    "nano-banana-2-lite": {
        "badge": "2 Lite",
        "recommended": False,
        "description": PRODUCT_DESCRIPTIONS["nano-banana-2-lite"],
        "order": 2,
    },
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


def _product_key(model: dict[str, Any]) -> str:
    presentation = model.get("presentation") if isinstance(model.get("presentation"), dict) else {}
    return str(presentation.get("product_key") or model.get("id") or "")


def _display_price_source(model: dict[str, Any]) -> Any:
    if model.get("admin_free") and model.get("retail_price_rox") is not None:
        return model.get("retail_price_rox")
    return model.get("price_rox") or model.get("price_credits") or "0"


def _price_value(model: dict[str, Any]) -> Decimal:
    return Decimal(str(_display_price_source(model)))


def _price_display(model: dict[str, Any]) -> str | None:
    if model.get("price_rox") is None and model.get("price_credits") is None:
        return None
    return format(_price_value(model), ".2f")


def _product_title(model: dict[str, Any]) -> str:
    presentation = model.get("presentation") if isinstance(model.get("presentation"), dict) else {}
    model_id = str(model.get("id") or "")
    return str(
        presentation.get("product_title")
        or presentation.get("title")
        or model.get("title")
        or model_id
    )


def _version_label(model: dict[str, Any]) -> str:
    presentation = model.get("presentation") if isinstance(model.get("presentation"), dict) else {}
    return str(presentation.get("version_label") or _product_title(model))


def _description_for(model: dict[str, Any]) -> str:
    model_id = str(model.get("id") or "")
    product_key = _product_key(model)
    presentation = model.get("presentation") if isinstance(model.get("presentation"), dict) else {}
    return str(
        PRODUCT_DESCRIPTIONS.get(product_key)
        or PRODUCT_DESCRIPTIONS.get(model_id)
        or presentation.get("product_title")
        or model.get("title")
        or model_id
    )


def _variant(model: dict[str, Any]) -> dict[str, Any]:
    model_id = str(model.get("id") or "")
    meta = VARIANT_META.get(model_id, {})
    title = _product_title(model)
    short_label = _version_label(model)
    badge = meta.get("badge")
    if badge is None and short_label != title:
        badge = short_label
    display_price = _price_display(model)
    return {
        "id": model_id,
        "title": title,
        "version": title,
        "operation": str(model.get("operation") or ""),
        "media_type": str(model.get("media_type") or ""),
        "price_rox": display_price,
        "price_credits": display_price,
        "price_rub": display_price,
        "retail_price_rox": model.get("retail_price_rox"),
        "effective_price_rox": model.get("effective_price_rox") or model.get("price_rox"),
        "admin_free": bool(model.get("admin_free")),
        "badge": badge,
        "recommended": bool(meta.get("recommended", False)),
        "description": meta.get("description") or _description_for(model),
        "ui_schema": model.get("ui_schema"),
        "order": int(meta.get("order", 1000)),
    }


def _preferred_public_model(models: list[dict[str, Any]]) -> dict[str, Any]:
    reference_capable = [
        item for item in models if str(item.get("id") or "") in PUBLIC_REFERENCE_OPTIONAL_MODEL_IDS
    ]
    if reference_capable:
        return sorted(reference_capable, key=lambda item: str(item.get("id") or ""))[0]
    return sorted(
        models,
        key=lambda item: (
            not bool(VARIANT_META.get(str(item.get("id") or ""), {}).get("recommended", False)),
            int(VARIANT_META.get(str(item.get("id") or ""), {}).get("order", 1000)),
            _price_value(item),
            str(item.get("title") or ""),
        ),
    )[0]


def _coalesced_variants(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for model in models:
        buckets.setdefault(_product_key(model), []).append(model)

    variants: list[dict[str, Any]] = []
    for product_models in buckets.values():
        chosen = _preferred_public_model(product_models)
        variant = _variant(chosen)
        product_prices = [
            _price_value(item)
            for item in product_models
            if item.get("price_rox") is not None
        ]
        if product_prices:
            variant["price_rox"] = format(min(product_prices), ".2f")
            variant["price_credits"] = variant["price_rox"]
            variant["price_rub"] = variant["price_rox"]
        is_auto = (
            len(product_models) > 1
            or str(chosen.get("id") or "") in PUBLIC_REFERENCE_OPTIONAL_MODEL_IDS
        )
        if is_auto:
            product_title = _product_title(chosen)
            variant["title"] = product_title
            variant["version"] = product_title
            variant["operation"] = "auto"
            variant["auto_mode"] = True
            variant["description"] = _description_for(chosen)
        variants.append(variant)
    return variants


def build_model_families(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped_models: dict[str, list[dict[str, Any]]] = {}
    for model in models:
        grouped_models.setdefault(_family_id(model), []).append(model)

    families: list[dict[str, Any]] = []
    for family_id, family_models in grouped_models.items():
        variants = _coalesced_variants(family_models)
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
                "media_types": sorted(
                    {str(item["media_type"]) for item in variants if item.get("media_type")}
                ),
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
