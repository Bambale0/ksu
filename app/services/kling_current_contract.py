from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from math import isfinite
from typing import Any
from urllib.parse import urlparse

from app.services import kie_video_contracts as video_contracts
from app.services import model_catalog as catalog
from app.services import model_ui

KLING_25_T2V_PROVIDER = "kling/v2-5-turbo-text-to-video-pro"
KLING_25_I2V_PROVIDER = "kling/v2-5-turbo-image-to-video-pro"
KLING_AVATAR_STANDARD_PROVIDER = "kling/ai-avatar-standard"
KLING_AVATAR_PRO_PROVIDER = "kling/ai-avatar-pro"

KLING_25_MODEL_IDS = {
    "kling-2.5-turbo-pro-t2v",
    "kling-2.5-turbo-pro-i2v",
}
KLING_AVATAR_MODEL_IDS = {
    "kling-avatar-standard",
    "kling-avatar-pro",
}
KLING_CURRENT_MODEL_IDS = KLING_25_MODEL_IDS | KLING_AVATAR_MODEL_IDS
KLING_CURRENT_PROVIDER_MODELS = {
    KLING_25_T2V_PROVIDER,
    KLING_25_I2V_PROVIDER,
    KLING_AVATAR_STANDARD_PROVIDER,
    KLING_AVATAR_PRO_PROVIDER,
}

# All catalog prices are public ROX. ROXY's product denomination is 1 ROX = 1 RUB;
# historical 10-RUB balances were migrated once and are never re-denominated here.
CURRENT_KLING_SPECS = (
    catalog.ModelSpec(
        "kling-2.5-turbo-pro-t2v",
        "Kling 2.5 Turbo Pro · Text to Video",
        "kling",
        KLING_25_T2V_PROVIDER,
        "video",
        "text_to_video",
        ("prompt", "duration", "aspect_ratio", "negative_prompt", "cfg_scale", "nsfw_checker"),
        ("prompt", "duration"),
        "per_second",
        Decimal("3"),
        5,
        10,
        "duration",
        ("Current Kie contract supports only 5s or 10s clips.",),
    ),
    catalog.ModelSpec(
        "kling-2.5-turbo-pro-i2v",
        "Kling 2.5 Turbo Pro · Image to Video",
        "kling",
        KLING_25_I2V_PROVIDER,
        "video",
        "image_to_video",
        (
            "prompt",
            "image_url",
            "tail_image_url",
            "duration",
            "negative_prompt",
            "cfg_scale",
            "nsfw_checker",
        ),
        ("prompt", "image_url", "duration"),
        "per_second",
        Decimal("3"),
        5,
        10,
        "duration",
        ("Optional tail frame is supported by the current Kie callable contract.",),
    ),
    catalog.ModelSpec(
        "kling-avatar-standard",
        "Kling AI Avatar · Standard",
        "kling",
        KLING_AVATAR_STANDARD_PROVIDER,
        "video",
        "audio_driven_avatar",
        ("image_url", "audio_url", "prompt"),
        ("image_url", "audio_url"),
        "per_second",
        Decimal("2"),
        1,
        300,
        None,
        (
            "720p avatar generation; billing_seconds must match the input audio duration.",
            "Kie's executable API example sends prompt as an empty string; guidance is optional.",
        ),
    ),
    catalog.ModelSpec(
        "kling-avatar-pro",
        "Kling AI Avatar · Pro",
        "kling",
        KLING_AVATAR_PRO_PROVIDER,
        "video",
        "audio_driven_avatar",
        ("image_url", "audio_url", "prompt"),
        ("image_url", "audio_url"),
        "per_second",
        Decimal("3"),
        1,
        300,
        None,
        (
            "1080p/48fps avatar generation; billing_seconds must match the input audio duration.",
            "Kie's executable API example sends prompt as an empty string; guidance is optional.",
        ),
    ),
)


def _https_url(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip()
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise catalog.InvalidModelParametersError(f"{field} must be an HTTPS URL")
    return normalized


def _number(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise catalog.InvalidModelParametersError(f"{field} must be numeric")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise catalog.InvalidModelParametersError(f"{field} must be numeric") from exc
    if not isfinite(normalized):
        raise catalog.InvalidModelParametersError(f"{field} must be finite")
    return normalized


def _validate_current_kling_rules(spec: catalog.ModelSpec, clean: dict[str, Any]) -> None:
    unknown = sorted(set(clean) - set(spec.known_fields))
    if unknown:
        raise catalog.InvalidModelParametersError(
            f"Unsupported {spec.id} fields: {', '.join(unknown)}"
        )

    if spec.id in KLING_25_MODEL_IDS:
        try:
            duration = int(clean.get("duration"))
        except (TypeError, ValueError) as exc:
            raise catalog.InvalidModelParametersError(
                "Kling 2.5 Turbo Pro duration must be 5 or 10 seconds"
            ) from exc
        if duration not in {5, 10}:
            raise catalog.InvalidModelParametersError(
                "Kling 2.5 Turbo Pro duration must be 5 or 10 seconds"
            )
        clean["duration"] = duration

        if clean.get("cfg_scale") not in (None, ""):
            clean["cfg_scale"] = _number(clean["cfg_scale"], field="cfg_scale")
        if clean.get("nsfw_checker") is not None and not isinstance(clean["nsfw_checker"], bool):
            raise catalog.InvalidModelParametersError("nsfw_checker must be boolean")
        for text_field in ("prompt", "negative_prompt"):
            if clean.get(text_field) is not None and not isinstance(clean[text_field], str):
                raise catalog.InvalidModelParametersError(f"{text_field} must be a string")

    if spec.id == "kling-2.5-turbo-pro-t2v":
        aspect_ratio = str(clean.get("aspect_ratio") or "16:9")
        if aspect_ratio not in {"16:9", "9:16", "1:1"}:
            raise catalog.InvalidModelParametersError(
                "Kling 2.5 Turbo Pro aspect_ratio must be 16:9, 9:16 or 1:1"
            )
        clean["aspect_ratio"] = aspect_ratio

    if spec.id == "kling-2.5-turbo-pro-i2v":
        clean["image_url"] = _https_url(clean.get("image_url"), field="image_url")
        if clean.get("tail_image_url") not in (None, ""):
            clean["tail_image_url"] = _https_url(
                clean["tail_image_url"], field="tail_image_url"
            )

    if spec.id in KLING_AVATAR_MODEL_IDS:
        clean["image_url"] = _https_url(clean.get("image_url"), field="image_url")
        clean["audio_url"] = _https_url(clean.get("audio_url"), field="audio_url")
        prompt = clean.get("prompt")
        if prompt is None:
            clean["prompt"] = ""
        elif not isinstance(prompt, str):
            raise catalog.InvalidModelParametersError("prompt must be a string")


def _contract_error(message: str) -> video_contracts.KieVideoContractError:
    return video_contracts.KieVideoContractError(message)


def _provider_https_url(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip()
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise _contract_error(f"{field} must be an HTTPS URL")
    return normalized


def _provider_number(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise _contract_error(f"{field} must be numeric")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise _contract_error(f"{field} must be numeric") from exc
    if not isfinite(normalized):
        raise _contract_error(f"{field} must be finite")
    return normalized


def normalize_current_kling_input(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(input_data)

    if model == KLING_25_T2V_PROVIDER:
        allowed = {
            "prompt",
            "duration",
            "aspect_ratio",
            "negative_prompt",
            "cfg_scale",
            "nsfw_checker",
        }
        required = {"prompt", "duration"}
    elif model == KLING_25_I2V_PROVIDER:
        allowed = {
            "prompt",
            "image_url",
            "tail_image_url",
            "duration",
            "negative_prompt",
            "cfg_scale",
            "nsfw_checker",
        }
        required = {"prompt", "image_url", "duration"}
    elif model in {KLING_AVATAR_STANDARD_PROVIDER, KLING_AVATAR_PRO_PROVIDER}:
        allowed = {"image_url", "audio_url", "prompt"}
        required = {"image_url", "audio_url"}
    else:
        return payload

    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise _contract_error(
            f"Unsupported fields for {model}: {', '.join(unknown)}"
        )
    for field in required:
        if payload.get(field) in (None, "", []):
            raise _contract_error(f"Missing required field: {field}")

    if model in {KLING_25_T2V_PROVIDER, KLING_25_I2V_PROVIDER}:
        duration = str(payload.get("duration") or "")
        if duration not in {"5", "10"}:
            raise _contract_error("Kling 2.5 Turbo Pro duration must be 5 or 10 seconds")
        payload["duration"] = duration
        if payload.get("cfg_scale") not in (None, ""):
            payload["cfg_scale"] = _provider_number(payload["cfg_scale"], field="cfg_scale")
        if payload.get("nsfw_checker") is not None and not isinstance(
            payload["nsfw_checker"], bool
        ):
            raise _contract_error("nsfw_checker must be boolean")

    if model == KLING_25_T2V_PROVIDER:
        aspect_ratio = str(payload.get("aspect_ratio") or "16:9")
        if aspect_ratio not in {"16:9", "9:16", "1:1"}:
            raise _contract_error(
                "Kling 2.5 Turbo Pro aspect_ratio must be 16:9, 9:16 or 1:1"
            )
        payload["aspect_ratio"] = aspect_ratio

    if model == KLING_25_I2V_PROVIDER:
        payload["image_url"] = _provider_https_url(payload["image_url"], field="image_url")
        if payload.get("tail_image_url") not in (None, ""):
            payload["tail_image_url"] = _provider_https_url(
                payload["tail_image_url"], field="tail_image_url"
            )

    if model in {KLING_AVATAR_STANDARD_PROVIDER, KLING_AVATAR_PRO_PROVIDER}:
        payload["image_url"] = _provider_https_url(payload["image_url"], field="image_url")
        payload["audio_url"] = _provider_https_url(payload["audio_url"], field="audio_url")
        prompt = payload.get("prompt")
        if prompt is None:
            payload["prompt"] = ""
        elif not isinstance(prompt, str):
            raise _contract_error("prompt must be a string")

    return payload


def _install_catalog_specs() -> None:
    existing_ids = {spec.id for spec in catalog.SPECS}
    additions = tuple(spec for spec in CURRENT_KLING_SPECS if spec.id not in existing_ids)
    if additions:
        catalog.SPECS = (*catalog.SPECS, *additions)
        catalog.ModelCatalog._by_id.update({spec.id: spec for spec in additions})


def _install_catalog_validation() -> None:
    if getattr(catalog.ModelCatalog, "_current_kling_validation_installed", False):
        return
    original = catalog.ModelCatalog._validate_model_rules

    def validate(spec: catalog.ModelSpec, clean: dict[str, Any]) -> None:
        original(spec, clean)
        if spec.id in KLING_CURRENT_MODEL_IDS:
            _validate_current_kling_rules(spec, clean)

    catalog.ModelCatalog._validate_model_rules = staticmethod(validate)
    catalog.ModelCatalog._current_kling_validation_installed = True


def _install_provider_contracts() -> None:
    if getattr(video_contracts, "_current_kling_contracts_installed", False):
        return
    original = video_contracts.normalize_kie_video_input
    video_contracts.VIDEO_MODELS.update(KLING_CURRENT_PROVIDER_MODELS)

    def normalize(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
        if model in KLING_CURRENT_PROVIDER_MODELS:
            return normalize_current_kling_input(model, input_data)
        return original(model, input_data)

    video_contracts.normalize_kie_video_input = normalize
    video_contracts._current_kling_contracts_installed = True


def _install_ui_contracts() -> None:
    model_ui.FIELD_DEFINITIONS.setdefault(
        "tail_image_url",
        {
            "label": "Последний кадр",
            "control": "file",
            "group": "references",
            "accept": "image/jpeg,image/png",
        },
    )

    kling_25_duration = {
        "label": "Длительность",
        "control": "combobox",
        "suggestions": ["5", "10"],
        "group": "output",
        "suffix": "с",
    }
    kling_25_common = {
        "duration": kling_25_duration,
        "cfg_scale": {"label": "CFG scale", "step": 0.1},
        "nsfw_checker": {"label": "NSFW-проверка"},
    }
    model_ui.MODEL_OVERRIDES.update(
        {
            "kling-2.5-turbo-pro-t2v": {
                "defaults": {
                    "duration": "5",
                    "aspect_ratio": "16:9",
                    "cfg_scale": 0.5,
                    "nsfw_checker": True,
                },
                "field_overrides": {
                    **kling_25_common,
                    "aspect_ratio": {
                        "suggestions": ["16:9", "9:16", "1:1"],
                    },
                },
            },
            "kling-2.5-turbo-pro-i2v": {
                "defaults": {
                    "duration": "5",
                    "cfg_scale": 0.5,
                    "nsfw_checker": True,
                },
                "field_overrides": {
                    **kling_25_common,
                    "image_url": {
                        "label": "Первый кадр",
                        "accept": "image/jpeg,image/png",
                        "max_size_mb": 10,
                    },
                    "tail_image_url": {
                        "label": "Последний кадр",
                        "accept": "image/jpeg,image/png",
                        "max_size_mb": 10,
                    },
                },
            },
            "kling-avatar-standard": {
                "field_overrides": {
                    "image_url": {
                        "label": "Фото аватара",
                        "accept": "image/jpeg,image/png",
                        "max_size_mb": 10,
                    },
                    "audio_url": {
                        "label": "Речь / пение",
                        "accept": "audio/mpeg,audio/wav,audio/x-wav,audio/aac,audio/mp4,audio/ogg",
                        "max_size_mb": 100,
                    },
                    "prompt": {
                        "label": "Эмоции и стиль движения",
                        "placeholder": "Опционально: спокойная подача, лёгкие движения головы...",
                    },
                },
                "billing_seconds": {
                    "label": "Длительность аудио",
                    "min": 1,
                    "max": 300,
                    "required": True,
                },
            },
            "kling-avatar-pro": {
                "field_overrides": {
                    "image_url": {
                        "label": "Фото аватара",
                        "accept": "image/jpeg,image/png",
                        "max_size_mb": 10,
                    },
                    "audio_url": {
                        "label": "Речь / пение",
                        "accept": "audio/mpeg,audio/wav,audio/x-wav,audio/aac,audio/mp4,audio/ogg",
                        "max_size_mb": 100,
                    },
                    "prompt": {
                        "label": "Эмоции и стиль движения",
                        "placeholder": "Опционально: энергичная подача, выразительная мимика...",
                    },
                },
                "billing_seconds": {
                    "label": "Длительность аудио",
                    "min": 1,
                    "max": 300,
                    "required": True,
                },
            },
        }
    )


def install_current_kling_contracts() -> None:
    """Register current Kie Kling 2.5 Turbo Pro and AI Avatar contracts.

    The existing catalog is intentionally extended at package initialization so
    the new provider contracts stay isolated from legacy Tanya payloads while all
    current KSU entry points (catalog, quote/create, provider adapter and UI schema)
    observe the same definitions.
    """

    _install_catalog_specs()
    _install_catalog_validation()
    _install_provider_contracts()
    _install_ui_contracts()
