from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from app.core.config import settings

MediaType = Literal["image", "video"]
PriceMode = Literal["flat", "per_second"]


class UnknownModelError(ValueError):
    pass


class InvalidModelParametersError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ModelSpec:
    id: str
    title: str
    family: str
    kie_model: str
    media_type: MediaType
    operation: str
    known_fields: tuple[str, ...]
    required_fields: tuple[str, ...] = ()
    price_mode: PriceMode = "flat"
    default_price_rox: Decimal = Decimal("10")
    min_seconds: int | None = None
    max_seconds: int | None = None
    duration_field: str | None = "duration"
    notes: tuple[str, ...] = ()

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "family": self.family,
            "kie_model": self.kie_model,
            "media_type": self.media_type,
            "operation": self.operation,
            "known_fields": list(self.known_fields),
            "required_fields": list(self.required_fields),
            "price_mode": self.price_mode,
            "price_rox": str(ModelCatalog.unit_price(self.id)),
            "min_seconds": self.min_seconds,
            "max_seconds": self.max_seconds,
            "notes": list(self.notes),
        }


# This is intentionally a strict product whitelist copied from the production
# selector in banano_kling:tanyapi. Do not add experimental/provider-only models
# here: the customer catalog should stay small and deliberate.
IMAGE_MODEL_IDS = (
    "nano-banana-2-lite",
    "seedream_5_pro",
    "banana_pro",
    "banana_2",
    "seedream_edit",
    "flux_pro",
    "wan_27",
    "grok_imagine_i2i",
)
VIDEO_MODEL_IDS = (
    "v3_pro",
    "v3_std",
    "v26_pro",
    "grok_imagine",
    "grok_imagine_v15",
    "seedance_2",
    "gemini_omni",
    "veo3_fast",
    "motion_control_v26",
    "motion_control_v30",
    "avatar_std",
    "avatar_pro",
)
PUBLIC_MODEL_IDS = IMAGE_MODEL_IDS + VIDEO_MODEL_IDS

SEEDANCE_FIELDS = (
    "prompt",
    "first_frame_url",
    "last_frame_url",
    "reference_image_urls",
    "reference_video_urls",
    "reference_audio_urls",
    "generate_audio",
    "aspect_ratio",
    "duration",
)
WAN_IMAGE_FIELDS = (
    "prompt",
    "input_urls",
    "n",
    "enable_sequential",
    "resolution",
    "thinking_mode",
    "watermark",
    "seed",
    "bbox_list",
)
KLING_3_FIELDS = (
    "prompt",
    "image_urls",
    "sound",
    "duration",
    "aspect_ratio",
    "multi_shots",
    "multi_prompt",
    "kling_elements",
)
GEMINI_OMNI_FIELDS = (
    "prompt",
    "image_urls",
    "audio_ids",
    "video_list",
    "character_ids",
    "duration",
    "resolution",
    "aspect_ratio",
)
VEO_FAST_FIELDS = (
    "prompt",
    "image_urls",
    "watermark_text",
    "aspect_ratio",
    "enable_fallback",
    "enable_translation",
    "generation_type",
    "duration",
)


SPECS: tuple[ModelSpec, ...] = (
    # Images — exact Tanya production selector.
    ModelSpec(
        "nano-banana-2-lite",
        "Nano Banana 2 Lite",
        "nanobanana",
        "nano-banana-2-lite",
        "image",
        "generate_or_edit",
        ("prompt", "image_urls", "aspect_ratio"),
        ("prompt",),
        default_price_rox=Decimal("10"),
    ),
    ModelSpec(
        "seedream_5_pro",
        "ByteDance Seedream 5 Pro",
        "seedream",
        "seedream/5-pro-text-to-image",
        "image",
        "generate_or_edit",
        ("prompt", "image_urls", "aspect_ratio", "quality", "output_format", "nsfw_checker"),
        ("prompt",),
        default_price_rox=Decimal("18"),
        notes=("Uses the image-to-image provider automatically when references are attached.",),
    ),
    ModelSpec(
        "banana_pro",
        "Google Nano Banana Pro",
        "nanobanana",
        "nano-banana-pro",
        "image",
        "generate_or_edit",
        ("prompt", "image_input", "aspect_ratio", "resolution", "output_format"),
        ("prompt",),
        default_price_rox=Decimal("20"),
    ),
    ModelSpec(
        "banana_2",
        "Google Nano Banana 2",
        "nanobanana",
        "nano-banana-2",
        "image",
        "generate_or_edit",
        ("prompt", "image_input", "aspect_ratio", "resolution", "output_format"),
        ("prompt",),
        default_price_rox=Decimal("15"),
    ),
    ModelSpec(
        "seedream_edit",
        "ByteDance Seedream 4.5 Edit",
        "seedream",
        "seedream/4.5-edit",
        "image",
        "image_edit",
        ("prompt", "image_urls", "aspect_ratio", "quality", "nsfw_checker"),
        ("prompt", "image_urls"),
        default_price_rox=Decimal("12"),
    ),
    ModelSpec(
        "flux_pro",
        "OpenAI GPT Image 2",
        "gpt-image",
        "gpt-image-2-text-to-image",
        "image",
        "generate_or_edit",
        ("prompt", "input_urls", "aspect_ratio", "resolution"),
        ("prompt",),
        default_price_rox=Decimal("20"),
        notes=("Uses GPT Image 2 image-to-image automatically when references are attached.",),
    ),
    ModelSpec(
        "wan_27",
        "Alibaba Wan 2.7 Pro",
        "wan",
        "wan/2-7-image-pro",
        "image",
        "generate_or_edit",
        WAN_IMAGE_FIELDS,
        ("prompt",),
        default_price_rox=Decimal("18"),
    ),
    ModelSpec(
        "grok_imagine_i2i",
        "Grok Imagine",
        "grok",
        "grok-imagine/image-to-image",
        "image",
        "image_to_image",
        ("prompt", "image_urls", "nsfw_checker"),
        ("prompt", "image_urls"),
        default_price_rox=Decimal("14"),
    ),

    # Video — exact Tanya production selector.
    ModelSpec(
        "v3_pro",
        "Kling 3.0 Pro",
        "kling",
        "kling-3.0/video",
        "video",
        "text_or_image_to_video",
        KLING_3_FIELDS,
        ("prompt", "duration"),
        "per_second",
        Decimal("15"),
        3,
        15,
    ),
    ModelSpec(
        "v3_std",
        "Kling 3.0 Standard",
        "kling",
        "kling-3.0/video",
        "video",
        "text_or_image_to_video",
        KLING_3_FIELDS,
        ("prompt", "duration"),
        "per_second",
        Decimal("15"),
        3,
        15,
    ),
    ModelSpec(
        "v26_pro",
        "Kling 2.5 Turbo Pro",
        "kling",
        "kling/v2-5-turbo-text-to-video-pro",
        "video",
        "text_or_image_to_video",
        ("prompt", "image_url", "negative_prompt", "cfg_scale", "duration", "aspect_ratio"),
        ("prompt", "duration"),
        "per_second",
        Decimal("15"),
        5,
        10,
        notes=("Only 5s and 10s durations are accepted.",),
    ),
    ModelSpec(
        "grok_imagine",
        "Grok Imagine",
        "grok",
        "grok-imagine/image-to-video",
        "video",
        "image_to_video",
        ("prompt", "image_urls", "mode", "duration", "resolution", "aspect_ratio", "nsfw_checker"),
        ("prompt", "duration"),
        "per_second",
        Decimal("11"),
        6,
        30,
    ),
    ModelSpec(
        "grok_imagine_v15",
        "Grok Imagine 1.5",
        "grok",
        "grok-imagine-video-1-5-preview",
        "video",
        "text_or_image_to_video",
        ("prompt", "image_urls", "duration", "resolution", "aspect_ratio", "nsfw_checker"),
        ("prompt", "duration"),
        "per_second",
        Decimal("12"),
        1,
        15,
    ),
    ModelSpec(
        "seedance_2",
        "Bytedance Seedance 2.0",
        "seedance",
        "bytedance/seedance-2",
        "video",
        "multimodal_video",
        SEEDANCE_FIELDS,
        ("prompt", "duration"),
        "per_second",
        Decimal("11"),
        5,
        15,
        notes=("Only 5s, 10s and 15s durations are accepted.",),
    ),
    ModelSpec(
        "gemini_omni",
        "Google Gemini Omni",
        "gemini",
        "gemini-omni-video",
        "video",
        "multimodal_video",
        GEMINI_OMNI_FIELDS,
        ("prompt", "duration"),
        "per_second",
        Decimal("14"),
        4,
        10,
        notes=("Supported durations: 4, 6, 8 and 10 seconds.",),
    ),
    ModelSpec(
        "veo3_fast",
        "Google Veo 3.1 Fast",
        "veo",
        "veo3_fast",
        "video",
        "text_or_image_to_video",
        VEO_FAST_FIELDS,
        ("prompt", "duration"),
        "per_second",
        Decimal("20"),
        6,
        6,
        notes=("Production selector exposes only Veo 3.1 Fast; duration is fixed at 6 seconds.",),
    ),
    ModelSpec(
        "motion_control_v26",
        "Kling Motion Control 2.6",
        "kling",
        "kling-2.6/motion-control",
        "video",
        "motion_control",
        ("prompt", "input_urls", "video_urls", "mode", "character_orientation"),
        ("input_urls", "video_urls"),
        "per_second",
        Decimal("13"),
        3,
        30,
        None,
        ("Billing duration is the reference motion-video duration.",),
    ),
    ModelSpec(
        "motion_control_v30",
        "Kling Motion Control 3.0",
        "kling",
        "kling-3.0/motion-control",
        "video",
        "motion_control",
        ("prompt", "input_urls", "video_urls", "mode", "character_orientation", "background_source"),
        ("input_urls", "video_urls"),
        "per_second",
        Decimal("15"),
        3,
        30,
        None,
        ("Billing duration is the reference motion-video duration.",),
    ),
    ModelSpec(
        "avatar_std",
        "Kling AI Avatar Standard",
        "kling",
        "kling/ai-avatar-standard",
        "video",
        "ai_avatar",
        ("image_url", "audio_url", "prompt"),
        ("image_url", "audio_url"),
        default_price_rox=Decimal("20"),
    ),
    ModelSpec(
        "avatar_pro",
        "Kling AI Avatar Pro",
        "kling",
        "kling/ai-avatar-pro",
        "video",
        "ai_avatar",
        ("image_url", "audio_url", "prompt"),
        ("image_url", "audio_url"),
        default_price_rox=Decimal("25"),
    ),
)


class ModelCatalog:
    _by_id = {spec.id: spec for spec in SPECS}

    @classmethod
    def get(cls, model_id: str) -> ModelSpec:
        try:
            return cls._by_id[model_id]
        except KeyError as exc:
            raise UnknownModelError(model_id) from exc

    @classmethod
    def list(cls) -> list[dict[str, Any]]:
        return [spec.public_dict() for spec in SPECS]

    @staticmethod
    def _pricing_overrides() -> dict[str, Any]:
        raw = settings.generation_pricing_json or "{}"
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("GENERATION_PRICING_JSON is not valid JSON") from exc
        return value if isinstance(value, dict) else {}

    @classmethod
    def unit_price(cls, model_id: str) -> Decimal:
        spec = cls.get(model_id)
        override = cls._pricing_overrides().get(model_id)
        if isinstance(override, dict):
            key = "per_second" if spec.price_mode == "per_second" else "flat"
            if key in override:
                return Decimal(str(override[key]))
        elif override is not None:
            return Decimal(str(override))
        return spec.default_price_rox

    @classmethod
    def resolve_provider_model(cls, model_id: str, parameters: dict[str, Any]) -> str:
        """Resolve the concrete Kie model for one public Tanya model.

        Tanya intentionally exposes one product card for several provider pairs.
        Store the resolved provider id on every generation so historical/in-flight
        jobs stay executable even after the public catalog changes again.
        """
        spec = cls.get(model_id)
        if model_id == "seedream_5_pro":
            return (
                "seedream/5-pro-image-to-image"
                if parameters.get("image_urls")
                else "seedream/5-pro-text-to-image"
            )
        if model_id == "flux_pro":
            return (
                "gpt-image-2-image-to-image"
                if parameters.get("input_urls")
                else "gpt-image-2-text-to-image"
            )
        if model_id == "v26_pro":
            return (
                "kling/v2-5-turbo-image-to-video-pro"
                if parameters.get("image_url")
                else "kling/v2-5-turbo-text-to-video-pro"
            )
        return spec.kie_model

    @staticmethod
    def _validate_model_rules(spec: ModelSpec, clean: dict[str, Any]) -> None:
        if spec.id in {"v3_std", "v3_pro"}:
            clean["mode"] = "std" if spec.id == "v3_std" else "pro"
            images = clean.get("image_urls") or []
            if not isinstance(images, list) or len(images) > 2:
                raise InvalidModelParametersError("Kling 3.0 accepts at most two frame images")
            elements = clean.get("kling_elements") or []
            if not isinstance(elements, list) or len(elements) > 3:
                raise InvalidModelParametersError("Kling 3.0 accepts at most three elements")
            if clean.get("multi_shots"):
                shots = clean.get("multi_prompt") or []
                if not isinstance(shots, list) or not 1 <= len(shots) <= 6:
                    raise InvalidModelParametersError("Kling multi-shot requires one to six shots")

        if spec.id == "v26_pro":
            if int(clean.get("duration") or 0) not in {5, 10}:
                raise InvalidModelParametersError("Kling 2.5 Turbo Pro duration must be 5 or 10 seconds")
            if clean.get("cfg_scale") not in (None, ""):
                try:
                    cfg = float(clean["cfg_scale"])
                except (TypeError, ValueError) as exc:
                    raise InvalidModelParametersError("Kling cfg_scale must be numeric") from exc
                if not 0 <= cfg <= 1:
                    raise InvalidModelParametersError("Kling cfg_scale must be between 0 and 1")
                clean["cfg_scale"] = round(cfg, 1)

        if spec.id == "seedance_2":
            if int(clean.get("duration") or 0) not in {5, 10, 15}:
                raise InvalidModelParametersError("Seedance 2.0 duration must be 5, 10 or 15 seconds")
            first = bool(clean.get("first_frame_url"))
            last = bool(clean.get("last_frame_url"))
            refs = any(clean.get(key) for key in ("reference_image_urls", "reference_video_urls", "reference_audio_urls"))
            if last and not first:
                raise InvalidModelParametersError("Seedance last frame requires a first frame")
            if (first or last) and refs:
                raise InvalidModelParametersError("Seedance frame mode and multimodal references are mutually exclusive")

        if spec.id == "gemini_omni":
            if int(clean.get("duration") or 0) not in {4, 6, 8, 10}:
                raise InvalidModelParametersError("Gemini Omni duration must be 4, 6, 8 or 10 seconds")
            images = clean.get("image_urls") or []
            videos = clean.get("video_list") or []
            characters = clean.get("character_ids") or []
            audio_ids = clean.get("audio_ids") or []
            if not all(isinstance(items, list) for items in (images, videos, characters, audio_ids)):
                raise InvalidModelParametersError("Gemini Omni media collections must be arrays")
            if len(videos) > 1 or len(characters) > 3 or len(audio_ids) > 1:
                raise InvalidModelParametersError("Gemini Omni media limits exceeded")
            if len(images) + len(videos) * 2 + len(characters) > 7:
                raise InvalidModelParametersError("Gemini Omni upload quota exceeds 7 units")

        if spec.id == "veo3_fast":
            clean["duration"] = 6
            clean["veo_model"] = "veo3_fast"
            images = clean.get("image_urls") or []
            if not isinstance(images, list) or len(images) > 3:
                raise InvalidModelParametersError("Veo 3.1 Fast accepts at most three image references")
            clean.setdefault("aspect_ratio", "16:9")
            if images and not clean.get("generation_type"):
                clean["generation_type"] = "REFERENCE_2_VIDEO"
            clean.setdefault("generation_type", "TEXT_2_VIDEO")

        if spec.operation == "motion_control":
            images = clean.get("input_urls") or []
            videos = clean.get("video_urls") or []
            if not isinstance(images, list) or len(images) != 1:
                raise InvalidModelParametersError("Kling Motion requires exactly one input image")
            if not isinstance(videos, list) or len(videos) != 1:
                raise InvalidModelParametersError("Kling Motion requires exactly one motion video")

        if spec.id == "grok_imagine":
            images = clean.get("image_urls") or []
            if not isinstance(images, list) or len(images) > 7:
                raise InvalidModelParametersError("Grok Imagine accepts at most seven image references")
            if int(clean.get("duration") or 0) not in {6, 10, 20, 30}:
                raise InvalidModelParametersError("Grok Imagine duration must be 6, 10, 20 or 30 seconds")

        if spec.id == "grok_imagine_v15":
            images = clean.get("image_urls") or []
            if not isinstance(images, list) or len(images) > 1:
                raise InvalidModelParametersError("Grok Imagine 1.5 accepts at most one start image")
            duration = int(clean.get("duration") or 0)
            if not 1 <= duration <= 15:
                raise InvalidModelParametersError("Grok Imagine 1.5 duration must be 1-15 seconds")

    @classmethod
    def prepare(
        cls,
        model_id: str,
        parameters: dict[str, Any],
        *,
        billing_seconds: int | None = None,
    ) -> tuple[ModelSpec, dict[str, Any], Decimal, int | None, Decimal]:
        spec = cls.get(model_id)
        clean = {key: value for key, value in parameters.items() if not key.startswith("_")}
        for field in spec.required_fields:
            if clean.get(field) in (None, "", []):
                raise InvalidModelParametersError(f"Missing required field: {field}")
        cls._validate_model_rules(spec, clean)

        unit_price = cls.unit_price(model_id)
        seconds: int | None = None
        if spec.price_mode == "per_second":
            candidate = clean.get(spec.duration_field) if spec.duration_field else None
            if candidate in (None, "", 0, "0"):
                candidate = billing_seconds
            try:
                seconds = int(candidate) if candidate is not None else None
            except (TypeError, ValueError) as exc:
                raise InvalidModelParametersError("Video duration must be an integer") from exc
            if seconds is None:
                raise InvalidModelParametersError("Video duration is required for billing")
            if spec.min_seconds is not None and seconds < spec.min_seconds:
                raise InvalidModelParametersError(f"Minimum duration is {spec.min_seconds}s")
            if spec.max_seconds is not None and seconds > spec.max_seconds:
                raise InvalidModelParametersError(f"Maximum duration is {spec.max_seconds}s")
            cost = (unit_price * Decimal(seconds)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            cost = unit_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if cost <= 0:
            raise InvalidModelParametersError("Model price must be positive")
        return spec, clean, cost, seconds, unit_price
