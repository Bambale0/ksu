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


SEEDANCE_FIELDS = (
    "prompt",
    "reference_image_urls",
    "reference_video_urls",
    "reference_audio_urls",
    "return_last_frame",
    "generate_audio",
    "resolution",
    "aspect_ratio",
    "duration",
    "fixed_lens",
    "web_search",
)
SEEDANCE_25_FIELDS = (
    "prompt",
    "reference_image_urls",
    "reference_video_urls",
    "reference_audio_urls",
    "return_last_frame",
    "generate_audio",
    "resolution",
    "aspect_ratio",
    "duration",
    "output_format",
    "web_search",
    "nsfw_checker",
)
VIDEO_COMMON = (
    "prompt",
    "negative_prompt",
    "resolution",
    "aspect_ratio",
    "duration",
    "seed",
    "watermark",
    "prompt_extend",
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
    "mode",
    "multi_shots",
    "multi_prompt",
    "kling_elements",
)
VEO_31_FIELDS = (
    "prompt",
    "image_urls",
    "veo_model",
    "watermark_text",
    "aspect_ratio",
    "enable_fallback",
    "enable_translation",
    "generation_type",
)
GEMINI_OMNI_FIELDS = (
    "prompt",
    "image_urls",
    "audio_ids",
    "video_list",
    "character_ids",
    "duration",
)


def _looks_like_kling_video_url(value: Any) -> bool:
    path = str(value or "").split("?", 1)[0].lower()
    return path.endswith((".mp4", ".mov", ".qt", ".quicktime"))


SPECS: tuple[ModelSpec, ...] = (
    # Nano Banana
    ModelSpec("nano-banana", "Nano Banana", "nanobanana", "google/nano-banana", "image", "text_to_image", ("prompt", "output_format", "aspect_ratio"), ("prompt",), default_price_rox=Decimal("8")),
    ModelSpec("nano-banana-edit", "Nano Banana Edit", "nanobanana", "google/nano-banana-edit", "image", "image_edit", ("prompt", "image_urls", "output_format", "aspect_ratio"), ("prompt", "image_urls"), default_price_rox=Decimal("10")),
    ModelSpec("nano-banana-pro", "NanoBanana PRO", "nanobanana", "nano-banana-pro", "image", "generate_or_edit", ("prompt", "image_input", "aspect_ratio", "resolution", "output_format"), ("prompt",), default_price_rox=Decimal("20")),
    ModelSpec("nano-banana-2", "NanoBanana 2", "nanobanana", "nano-banana-2", "image", "generate_or_edit", ("prompt", "image_input", "aspect_ratio", "resolution", "output_format"), ("prompt",), default_price_rox=Decimal("15")),
    ModelSpec("nano-banana-2-lite", "NanoBanana 2 Lite", "nanobanana", "nano-banana-2-lite", "image", "generate_or_edit", ("prompt", "image_urls", "aspect_ratio"), ("prompt",), default_price_rox=Decimal("10")),

    # Seedream
    ModelSpec("seedream-3-t2i", "Seedream 3.0 · Text to Image", "seedream", "bytedance/seedream", "image", "text_to_image", ("prompt", "image_size", "guidance_scale", "seed"), ("prompt",), default_price_rox=Decimal("8")),
    ModelSpec("seedream-4-t2i", "Seedream 4.0 · Text to Image", "seedream", "bytedance/seedream-v4-text-to-image", "image", "text_to_image", ("prompt", "image_size", "image_resolution", "max_images", "seed", "nsfw_checker"), ("prompt",), default_price_rox=Decimal("9")),
    ModelSpec("seedream-4-edit", "Seedream 4.0 · Edit", "seedream", "bytedance/seedream-v4-edit", "image", "image_edit", ("prompt", "image_urls", "image_size", "image_resolution", "max_images", "seed", "nsfw_checker"), ("prompt", "image_urls"), default_price_rox=Decimal("10")),
    ModelSpec("seedream-4.5-t2i", "Seedream 4.5", "seedream", "seedream/4.5-text-to-image", "image", "text_to_image", ("prompt", "aspect_ratio", "quality", "nsfw_checker"), ("prompt",), default_price_rox=Decimal("10")),
    ModelSpec("seedream-4.5-edit", "Seedream 4.5 · Edit", "seedream", "seedream/4.5-edit", "image", "image_edit", ("prompt", "image_urls", "aspect_ratio", "quality", "nsfw_checker"), ("prompt", "image_urls"), default_price_rox=Decimal("12")),
    ModelSpec("seedream-5-lite-t2i", "Seedream 5.0 Lite · Text to Image", "seedream", "seedream/5-lite-text-to-image", "image", "text_to_image", ("prompt", "aspect_ratio", "quality", "nsfw_checker"), ("prompt",), default_price_rox=Decimal("10")),
    ModelSpec("seedream-5-lite-i2i", "Seedream 5.0 Lite · Image to Image", "seedream", "seedream/5-lite-image-to-image", "image", "image_to_image", ("prompt", "image_urls", "aspect_ratio", "quality", "nsfw_checker"), ("prompt", "image_urls"), default_price_rox=Decimal("12")),
    ModelSpec("seedream-5-pro-t2i", "Seedream 5 Pro", "seedream", "seedream/5-pro-text-to-image", "image", "text_to_image", ("prompt", "aspect_ratio", "quality", "output_format", "nsfw_checker"), ("prompt",), default_price_rox=Decimal("16")),
    ModelSpec("seedream-5-pro-i2i", "Seedream 5 Pro · Image to Image", "seedream", "seedream/5-pro-image-to-image", "image", "image_to_image", ("prompt", "image_urls", "aspect_ratio", "quality", "output_format", "nsfw_checker"), ("prompt", "image_urls"), default_price_rox=Decimal("18")),
    ModelSpec("seedream-5-pro-layers", "Seedream 5 Pro · Layer Decomposition", "seedream", "seedream/5-pro-layer-decomposition", "image", "layer_decomposition", ("prompt", "image_url", "size", "output_format"), ("prompt", "image_url"), default_price_rox=Decimal("18")),

    # GPT Image
    ModelSpec("gpt-image-1.5-t2i", "GPT Image 1.5 · Text to Image", "gpt-image", "gpt-image/1.5-text-to-image", "image", "text_to_image", ("prompt", "aspect_ratio", "quality"), ("prompt",), default_price_rox=Decimal("14")),
    ModelSpec("gpt-image-1.5-i2i", "GPT Image 1.5 · Image to Image", "gpt-image", "gpt-image/1.5-image-to-image", "image", "image_to_image", ("prompt", "input_urls", "aspect_ratio", "quality"), ("prompt", "input_urls"), default_price_rox=Decimal("16")),
    ModelSpec("gpt-image-2-t2i", "GPT Image 2", "gpt-image", "gpt-image-2-text-to-image", "image", "text_to_image", ("prompt", "aspect_ratio"), ("prompt",), default_price_rox=Decimal("18")),
    ModelSpec("gpt-image-2-i2i", "GPT Image 2 · Image to Image", "gpt-image", "gpt-image-2-image-to-image", "image", "image_to_image", ("prompt", "input_urls", "aspect_ratio"), ("prompt", "input_urls"), default_price_rox=Decimal("20")),

    # Wan 2.7 images and full video modes
    ModelSpec("wan-2.7-image", "WAN 2.7", "wan", "wan/2-7-image", "image", "generate_or_edit", WAN_IMAGE_FIELDS, ("prompt",), default_price_rox=Decimal("12")),
    ModelSpec("wan-2.7-image-pro", "WAN 2.7 Pro", "wan", "wan/2-7-image-pro", "image", "generate_or_edit", WAN_IMAGE_FIELDS, ("prompt",), default_price_rox=Decimal("18")),
    ModelSpec("wan-2.7-t2v", "Wan 2.7 · Text to Video", "wan", "wan/2-7-text-to-video", "video", "text_to_video", VIDEO_COMMON + ("audio_url", "ratio"), ("prompt", "duration"), "per_second", Decimal("10"), 1, 30),
    ModelSpec("wan-2.7-i2v", "Wan 2.7 · Image to Video", "wan", "wan/2-7-image-to-video", "video", "image_to_video", VIDEO_COMMON + ("first_frame_url", "last_frame_url", "first_clip_url", "driving_audio_url"), ("prompt", "duration"), "per_second", Decimal("12"), 1, 30, notes=("Provide first_frame_url, first+last frames, or first_clip_url for continuation.",)),
    ModelSpec("wan-2.7-video-edit", "Wan 2.7 · Video Edit", "wan", "wan/2-7-videoedit", "video", "video_edit", VIDEO_COMMON + ("video_url", "reference_image", "audio_setting"), ("prompt", "video_url"), "per_second", Decimal("14"), 1, 60, notes=("When provider duration is 0/auto, billing_seconds is required.",)),
    ModelSpec("wan-2.7-r2v", "Wan 2.7 · Reference to Video", "wan", "wan/2-7-r2v", "video", "reference_to_video", VIDEO_COMMON + ("reference_image", "reference_video", "first_frame", "reference_voice"), ("prompt", "duration"), "per_second", Decimal("15"), 1, 30),

    # Seedance
    ModelSpec("seedance-1.5-pro", "Seedance 1.5 Pro", "seedance", "bytedance/seedance-1.5-pro", "video", "text_or_image_to_video", ("prompt", "input_urls", "aspect_ratio", "resolution", "duration", "fixed_lens", "generate_audio", "nsfw_checker"), ("prompt", "duration"), "per_second", Decimal("10"), 1, 30),
    ModelSpec("seedance-2.0", "Seedance 2.0", "seedance", "bytedance/seedance-2", "video", "multimodal_video", SEEDANCE_FIELDS, ("prompt", "duration"), "per_second", Decimal("50"), 4, 15),
    ModelSpec("seedance-2.0-fast", "Seedance 2.0 Fast", "seedance", "bytedance/seedance-2-fast", "video", "multimodal_video", SEEDANCE_FIELDS, ("prompt", "duration"), "per_second", Decimal("9"), 4, 15),
    ModelSpec("seedance-2.0-mini", "Seedance 2.0 Mini", "seedance", "bytedance/seedance-2-mini", "video", "multimodal_video", SEEDANCE_FIELDS, ("prompt", "duration"), "per_second", Decimal("8"), 4, 15),
    ModelSpec("seedance-2.5", "Seedance 2.5", "seedance", "bytedance/seedance-2-5", "video", "multimodal_video", SEEDANCE_25_FIELDS, ("prompt", "duration"), "per_second", Decimal("60"), 4, 30),

    # Kling 3.0 + Motion Control
    ModelSpec("kling-3.0", "Kling 3.0", "kling", "kling-3.0/video", "video", "text_or_image_to_video", KLING_3_FIELDS, ("duration",), "per_second", Decimal("15"), 3, 15, notes=("Single-shot supports up to first+last frame; multi-shot uses multi_prompt; up to three element references.",)),
    ModelSpec("kling-motion-2.6", "Kling Motion 2.6", "kling", "kling-2.6/motion-control", "video", "motion_control", ("prompt", "input_urls", "video_urls", "mode", "character_orientation"), ("prompt", "input_urls", "video_urls"), "per_second", Decimal("13"), 3, 30, None, ("Exactly one reference image and one 3-30s motion video.",)),
    ModelSpec("kling-motion-3.0", "Kling Motion 3.0", "kling", "kling-3.0/motion-control", "video", "motion_control", ("prompt", "input_urls", "video_urls", "mode", "character_orientation", "background_source"), ("prompt", "input_urls", "video_urls"), "per_second", Decimal("15"), 3, 30, None, ("Exactly one reference image and one 3-30s motion video.",)),

    # Veo 3.1 uses Kie's dedicated Veo API (not Market createTask).
    ModelSpec("veo-3.1", "Veo 3.1", "veo", "veo3_fast", "video", "text_or_image_to_video", VEO_31_FIELDS, ("prompt",), "per_second", Decimal("20"), 1, 30, None, ("Supports Veo 3.1 quality/fast/lite and text, first-last-frame, or reference generation modes.",)),

    # Gemini Omni Video
    ModelSpec("gemini-omni-video", "Gemini Omni", "gemini", "gemini-omni-video", "video", "multimodal_video", GEMINI_OMNI_FIELDS, ("prompt", "duration"), "per_second", Decimal("14"), 1, 30, notes=("Upload quota: images + 2×videos + character IDs must not exceed 7; maximum one video and three character IDs.",)),

    # Grok Imagine images + all video operations
    ModelSpec("grok-image-t2i", "Grok Imagine · Text to Image", "grok", "grok-imagine/text-to-image", "image", "text_to_image", ("prompt", "aspect_ratio"), ("prompt",), default_price_rox=Decimal("12")),
    ModelSpec("grok-image-i2i", "Grok Imagine · Image to Image", "grok", "grok-imagine/image-to-image", "image", "image_to_image", ("prompt", "image_urls"), ("prompt", "image_urls"), default_price_rox=Decimal("14")),
    ModelSpec("grok-video-t2v", "Grok", "grok", "grok-imagine/text-to-video", "video", "text_to_video", ("prompt", "aspect_ratio", "mode", "duration", "resolution"), ("prompt", "duration"), "per_second", Decimal("10"), 1, 30),
    ModelSpec("grok-video-i2v", "Grok · Image to Video", "grok", "grok-imagine/image-to-video", "video", "image_to_video", ("task_id", "image_urls", "prompt", "mode", "duration", "resolution", "aspect_ratio"), ("prompt", "image_urls", "duration"), "per_second", Decimal("11"), 1, 30),
    ModelSpec("grok-video-1.5", "Grok Imagine 1.5", "grok", "grok-imagine-video-1-5-preview", "video", "text_or_image_to_video", ("prompt", "image_urls", "aspect_ratio", "resolution", "duration"), ("prompt", "duration"), "per_second", Decimal("12"), 1, 30),
    ModelSpec("grok-video-upscale", "Grok Imagine · Video Upscale", "grok", "grok-imagine/upscale", "video", "video_upscale", ("task_id",), ("task_id",), "per_second", Decimal("5"), 1, 600, None, ("task_id must reference a video generated by Kie AI.",)),
    ModelSpec("grok-video-extend", "Grok Imagine · Video Extend", "grok", "grok-imagine/extend", "video", "video_extend", ("task_id", "prompt", "extend_at", "extend_times"), ("task_id",), "per_second", Decimal("10"), 1, 60, None, ("task_id must reference a video generated by Kie AI; billing_seconds is the billed extension length.",)),
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

    @staticmethod
    def _validate_model_rules(spec: ModelSpec, clean: dict[str, Any]) -> None:
        if spec.family == "seedance" and spec.id != "seedance-1.5-pro":
            # Frame mode is disabled product-wide: Kie rejects Seedance 2.5
            # frame tasks with a non-adaptive ratio (422) and frame/reference
            # mixing caused recurring submission failures. Multimodal
            # reference mode is the only supported image-input scenario.
            if clean.get("first_frame_url") or clean.get("last_frame_url"):
                raise InvalidModelParametersError(
                    "Seedance supports multimodal reference mode only; frame mode is disabled"
                )

        if spec.id == "seedance-1.5-pro":
            images = clean.get("input_urls") or []
            if not isinstance(images, list) or len(images) > 2:
                raise InvalidModelParametersError("Seedance 1.5 Pro accepts at most two input images")

        if spec.operation == "motion_control":
            images = clean.get("input_urls") or []
            videos = clean.get("video_urls") or []
            if not isinstance(images, list) or len(images) != 1:
                raise InvalidModelParametersError("Kling Motion requires exactly one input image")
            if not isinstance(videos, list) or len(videos) != 1:
                raise InvalidModelParametersError("Kling Motion requires exactly one motion video")

        if spec.id == "wan-2.7-i2v":
            first = bool(clean.get("first_frame_url"))
            last = bool(clean.get("last_frame_url"))
            clip = bool(clean.get("first_clip_url"))
            if not (first or clip):
                raise InvalidModelParametersError(
                    "Wan 2.7 image-to-video requires first_frame_url or first_clip_url"
                )
            if last and not first:
                raise InvalidModelParametersError("Wan 2.7 last frame requires a first frame")
            if clip and (first or last):
                raise InvalidModelParametersError(
                    "Wan 2.7 continuation cannot be combined with first/last frames"
                )

        if spec.id == "kling-3.0":
            images = clean.get("image_urls") or []
            if not isinstance(images, list) or len(images) > 2:
                raise InvalidModelParametersError("Kling 3.0 accepts at most two frame images")
            if clean.get("multi_shots") and len(images) > 1:
                raise InvalidModelParametersError(
                    "Kling multi-shot supports only the first frame image"
                )
            elements = clean.get("kling_elements") or []
            if not isinstance(elements, list) or len(elements) > 3:
                raise InvalidModelParametersError("Kling 3.0 accepts at most three elements")
            for element in elements:
                if not isinstance(element, dict):
                    raise InvalidModelParametersError("Kling elements must be objects")
                if not str(element.get("name") or "").strip():
                    raise InvalidModelParametersError("Every Kling element requires a name")
                refs = element.get("element_input_urls") or []
                audio_refs = element.get("element_input_audio_urls") or []
                if not isinstance(refs, list) or not isinstance(audio_refs, list):
                    raise InvalidModelParametersError("Kling element references must be arrays")
                if len(refs) > 4 or len(audio_refs) > 1 or (not refs and not audio_refs):
                    raise InvalidModelParametersError(
                        "Kling element requires one video, 2-4 images, or one audio reference"
                    )
                if len(refs) == 1:
                    has_times = all(key in element for key in ("start_time", "end_time"))
                    if not has_times and not _looks_like_kling_video_url(refs[0]):
                        raise InvalidModelParametersError(
                            "Kling single URL element must be an MP4/MOV video reference"
                        )
                    if has_times:
                        try:
                            start = int(element.get("start_time") or 0)
                            end = int(element.get("end_time") or 0)
                        except (TypeError, ValueError) as exc:
                            raise InvalidModelParametersError(
                                "Kling video element start/end must be milliseconds"
                            ) from exc
                        if start < 0 or end <= start or end - start < 3000 or end - start > 8000:
                            raise InvalidModelParametersError(
                                "Kling video element segment must be 3-8 seconds"
                            )
                elif refs and not 2 <= len(refs) <= 4:
                    raise InvalidModelParametersError(
                        "Kling image element requires 2-4 reference images"
                    )
            if clean.get("multi_shots"):
                shots = clean.get("multi_prompt") or []
                if not isinstance(shots, list) or not 1 <= len(shots) <= 6:
                    raise InvalidModelParametersError("Kling multi-shot requires one to six shots")
                total = 0
                for shot in shots:
                    if not isinstance(shot, dict) or not str(shot.get("prompt") or "").strip():
                        raise InvalidModelParametersError("Every Kling shot requires a prompt")
                    try:
                        shot_duration = int(shot.get("duration"))
                    except (TypeError, ValueError) as exc:
                        raise InvalidModelParametersError(
                            "Every Kling shot requires an integer duration"
                        ) from exc
                    if not 1 <= shot_duration <= 12:
                        raise InvalidModelParametersError("Kling shot duration must be 1-12 seconds")
                    if len(str(shot.get("prompt") or "")) > 500:
                        raise InvalidModelParametersError("Kling shot prompt must be at most 500 chars")
                    total += shot_duration
                if clean.get("duration") not in (None, "") and total != int(clean["duration"]):
                    raise InvalidModelParametersError(
                        "Kling multi-shot durations must add up to total duration"
                    )

        if spec.id == "gemini-omni-video":
            images = clean.get("image_urls") or []
            videos = clean.get("video_list") or []
            characters = clean.get("character_ids") or []
            audio_ids = clean.get("audio_ids") or []
            if not all(
                isinstance(items, list)
                for items in (images, videos, characters, audio_ids)
            ):
                raise InvalidModelParametersError(
                    "Gemini Omni media and ID collections must be arrays"
                )
            if len(videos) > 1:
                raise InvalidModelParametersError("Gemini Omni accepts at most one video")
            if len(characters) > 3:
                raise InvalidModelParametersError("Gemini Omni accepts at most three character IDs")
            if len(images) + len(videos) * 2 + len(characters) > 7:
                raise InvalidModelParametersError("Gemini Omni upload quota exceeds 7 units")
            for video in videos:
                if not isinstance(video, dict) or not str(video.get("url") or "").strip():
                    raise InvalidModelParametersError("Gemini Omni video item requires a URL")

        if spec.id == "veo-3.1":
            images = clean.get("image_urls") or []
            if not isinstance(images, list) or len(images) > 3:
                raise InvalidModelParametersError("Veo 3.1 accepts at most three image references")
            veo_model = str(clean.get("veo_model") or "veo3_fast")
            if veo_model not in {"veo3", "veo3_fast", "veo3_lite", "veo3_fast_r2v", "veo3_r2v"}:
                raise InvalidModelParametersError("Unsupported Veo 3.1 model variant")
            aspect_ratio = str(clean.get("aspect_ratio") or "16:9")
            if aspect_ratio not in {"auto", "16:9", "9:16"}:
                raise InvalidModelParametersError("Unsupported Veo 3.1 aspect ratio")
            generation_type = str(clean.get("generation_type") or "TEXT_2_VIDEO")
            if generation_type not in {
                "TEXT_2_VIDEO",
                "FIRST_AND_LAST_FRAMES_2_VIDEO",
                "REFERENCE_2_VIDEO",
            }:
                raise InvalidModelParametersError("Unsupported Veo 3.1 generation type")
            if generation_type == "FIRST_AND_LAST_FRAMES_2_VIDEO" and not 1 <= len(images) <= 2:
                raise InvalidModelParametersError(
                    "Veo first/last-frame generation requires one or two images"
                )
            if generation_type == "REFERENCE_2_VIDEO":
                if not images:
                    raise InvalidModelParametersError("Veo reference generation requires image references")
                if veo_model not in {"veo3_fast", "veo3_lite", "veo3_fast_r2v", "veo3_r2v"}:
                    raise InvalidModelParametersError(
                        "Veo reference generation is available only on Fast/Lite variants"
                    )

    @classmethod
    def prepare(
        cls,
        model_id: str,
        parameters: dict[str, Any],
        *,
        billing_seconds: int | None = None,
    ) -> tuple[ModelSpec, dict[str, Any], Decimal, int | None, Decimal]:
        spec = cls.get(model_id)
        clean = {k: v for k, v in parameters.items() if not k.startswith("_")}
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
            cost = (unit_price * Decimal(seconds)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            cost = unit_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if cost <= 0:
            raise InvalidModelParametersError("Model price must be positive")
        return spec, clean, cost, seconds, unit_price
