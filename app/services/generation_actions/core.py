from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.models import Generation
from app.services.model_capability import (
    MODE_IMAGE_TO_IMAGE,
    MODE_IMAGE_TO_VIDEO,
    ModelCapabilityResolver,
)
from app.services.model_catalog import ModelCatalog, ModelSpec, UnknownModelError
from app.services.model_routing import image_references, video_references
from app.services.model_ui_contract import build_public_model_ui_schema
from app.services.music_generation import MusicGenerationService


@dataclass(frozen=True, slots=True)
class GenerationAction:
    id: str
    label: str
    derivative: bool = True

    def public_dict(self) -> dict[str, object]:
        return {"id": self.id, "label": self.label, "derivative": self.derivative}


IMAGE_ACTIONS: tuple[GenerationAction, ...] = (
    GenerationAction("remix", "✨ Ремикс"),
    GenerationAction("repeat", "🔁 Ещё вариант"),
    GenerationAction("edit", "💅 Изменить образ"),
    GenerationAction("animate", "🎬 Оживить"),
    GenerationAction("publish", "📤 Опубликовать", derivative=False),
)

VIDEO_AUDIO_ACTIONS: tuple[GenerationAction, ...] = (
    GenerationAction("repeat", "🔄 Ещё вариант"),
    GenerationAction("new_prompt", "✏️ Новый промпт"),
    GenerationAction("parameters", "⚙️ Изменить параметры"),
    GenerationAction("publish", "📤 Опубликовать", derivative=False),
)

DERIVATIVE_ACTIONS = frozenset({"remix", "repeat", "edit", "animate", "new_prompt", "parameters"})
ACTION_ALIASES = {"new_prompt": "repeat", "parameters": "repeat"}

_SEEDANCE_20_IDS = frozenset({"seedance-2.0", "seedance-2.0-fast", "seedance-2.0-mini"})

_EDIT_FOCUS = {
    "clothes": "the clothing/outfit",
    "hair": "the hairstyle",
    "hair_color": "the hair color",
    "nails": "the nails/manicure",
    "background": "the background",
    "style": "the visual style",
    "details": "the requested details",
    "custom": "only the requested part",
}


class GenerationActionService:
    @staticmethod
    def media_type(generation: Generation) -> str:
        params = generation.parameters or {}
        stored = str(params.get("_media_type") or "").strip()
        if stored:
            return stored
        model_id = str(params.get("_model_id") or "").strip()
        if model_id:
            try:
                return ModelCatalog.get(model_id).media_type
            except UnknownModelError:
                pass
        if generation.kind in {"image", "video", "audio", "music"}:
            return "audio" if generation.kind == "music" else generation.kind
        return "image"

    @staticmethod
    def model_id(generation: Generation) -> str:
        return str((generation.parameters or {}).get("_model_id") or "").strip()

    @staticmethod
    def result_url(generation: Generation) -> str | None:
        if generation.result_url:
            return str(generation.result_url)
        raw = (generation.parameters or {}).get("_result_urls")
        if isinstance(raw, list):
            for value in raw:
                text = str(value or "").strip()
                if text:
                    return text
        return None

    @classmethod
    def available_actions(cls, generation: Generation) -> list[GenerationAction]:
        if generation.status != "succeeded" or not cls.result_url(generation):
            return []
        media_type = cls.media_type(generation)
        source = IMAGE_ACTIONS if media_type == "image" else VIDEO_AUDIO_ACTIONS

        # Admin trend/template prompts and source references are server-owned secrets.
        # The rendered result may still be remixed/edited/animated, but a workflow
        # that reconstructs the recipe is not available.
        if generation.action_type == "trend":
            if media_type == "image":
                source = tuple(
                    item for item in source if item.id in {"remix", "edit", "animate", "publish"}
                )
            else:
                source = tuple(item for item in source if item.id == "publish")

        # Capability checks remain server-side. If the current catalog has no
        # executable model for a derivative action, do not render a dead button.
        result: list[GenerationAction] = []
        for item in source:
            if item.derivative and not cls.public_candidates(generation, item.id):
                continue
            result.append(item)
        return result

    @classmethod
    def action_allowed(cls, generation: Generation, action: str) -> bool:
        return action in {item.id for item in cls.available_actions(generation)}

    @staticmethod
    def canonical_action(action: str) -> str:
        return ACTION_ALIASES.get(action, action)

    @staticmethod
    def _supports_image_source(spec: ModelSpec) -> bool:
        return ModelCapabilityResolver.supports_input(spec, "image") and not (
            ModelCapabilityResolver.consumes_source_media(spec)
        )

    @classmethod
    def candidate_specs(cls, generation: Generation, action: str) -> list[ModelSpec]:
        action = cls.canonical_action(action)
        media_type = cls.media_type(generation)
        if action in {"remix", "edit"}:
            return ModelCapabilityResolver.compatible_specs(media_type, MODE_IMAGE_TO_IMAGE)
        if action == "animate":
            return ModelCapabilityResolver.compatible_specs(media_type, MODE_IMAGE_TO_VIDEO)
        if action == "repeat":
            specs = [ModelCatalog.get(str(item["id"])) for item in ModelCatalog.list()]
            return [spec for spec in specs if spec.media_type == media_type]
        return []

    @classmethod
    def public_candidates(cls, generation: Generation, action: str) -> list[dict[str, Any]]:
        if cls.media_type(generation) == "audio" and cls.canonical_action(action) == "repeat":
            model = MusicGenerationService.public_model()
            return [model]
        result: list[dict[str, Any]] = []
        for spec in cls.candidate_specs(generation, action):
            item = spec.public_dict()
            item["ui_schema"] = build_public_model_ui_schema(item)
            result.append(item)
        return result

    @classmethod
    def default_model_id(cls, generation: Generation, action: str) -> str | None:
        candidates = cls.public_candidates(generation, action)
        if not candidates:
            return None
        candidate_ids = {str(item["id"]) for item in candidates}
        current_id = cls.model_id(generation)
        canonical = cls.canonical_action(action)
        if canonical == "repeat" and current_id in candidate_ids:
            return current_id
        if canonical in {"remix", "edit"}:
            if current_id in candidate_ids:
                return current_id
            try:
                current_family = ModelCatalog.get(current_id).family
            except UnknownModelError:
                current_family = ""
            same_family = next(
                (
                    str(item["id"])
                    for item in candidates
                    if str(item.get("family") or "") == current_family
                ),
                None,
            )
            if same_family:
                return same_family
        if canonical == "animate":
            for preferred in ("grok-video-i2v", "grok-video-1.5"):
                if preferred in candidate_ids:
                    return preferred
        return str(candidates[0]["id"])

    @classmethod
    def reusable_parameters(cls, generation: Generation, model_id: str) -> dict[str, Any]:
        params = dict(generation.parameters or {})
        if MusicGenerationService.is_music_model(model_id):
            return MusicGenerationService.reusable_parameters(params)
        try:
            spec = ModelCatalog.get(model_id)
        except UnknownModelError:
            return {}
        allowed = set(spec.known_fields)
        return {
            key: value
            for key, value in params.items()
            if key in allowed and key != "prompt" and not key.startswith("_")
        }

    @staticmethod
    def parent_references(generation: Generation) -> tuple[list[str], list[str]]:
        # Trend/template recipes are intentionally not disclosed through the
        # derivative context. Remix/edit/animate use the rendered result URL as
        # their explicit source, so hiding these recipe references loses no UX.
        if generation.action_type == "trend":
            return [], []
        params = dict(generation.parameters or {})
        return image_references(params, generation.input_url), video_references(params)

    @staticmethod
    def _adapt_seedance_references(
        generation: Generation,
        target: ModelSpec,
        parameters: dict[str, Any],
        images: list[str],
        videos: list[str],
    ) -> dict[str, Any]:
        result = dict(parameters)
        source = dict(generation.parameters or {})
        fields = set(target.known_fields)

        if target.id == "seedance-2.5":
            # Seedance 2.5 keeps frame mode and multimodal-reference mode mutually
            # exclusive. Prefer the parent's explicit reference mode when present;
            # otherwise preserve temporal frames.
            has_reference_mode = any(
                source.get(name)
                for name in (
                    "reference_image_urls",
                    "reference_video_urls",
                    "reference_audio_urls",
                )
            )
            if has_reference_mode:
                for name in (
                    "reference_image_urls",
                    "reference_video_urls",
                    "reference_audio_urls",
                ):
                    if name in fields and source.get(name):
                        result.setdefault(name, source[name])
                if not any(result.get(name) for name in ("reference_image_urls", "reference_video_urls")):
                    if images and "reference_image_urls" in fields:
                        result.setdefault("reference_image_urls", images)
                    if videos and "reference_video_urls" in fields:
                        result.setdefault("reference_video_urls", videos)
            else:
                if source.get("first_frame_url") and "first_frame_url" in fields:
                    result.setdefault("first_frame_url", source["first_frame_url"])
                elif images and "first_frame_url" in fields:
                    result.setdefault("first_frame_url", images[0])
                if source.get("last_frame_url") and "last_frame_url" in fields:
                    result.setdefault("last_frame_url", source["last_frame_url"])
            return result

        if target.id in _SEEDANCE_20_IDS:
            # Seedance 2.0 supports hybrid first/last frames plus multimodal refs.
            for name in (
                "first_frame_url",
                "last_frame_url",
                "reference_image_urls",
                "reference_video_urls",
                "reference_audio_urls",
            ):
                if name in fields and source.get(name):
                    result.setdefault(name, source[name])
            if images and not result.get("first_frame_url") and not result.get("reference_image_urls"):
                result.setdefault("reference_image_urls", images)
            if videos and not result.get("reference_video_urls"):
                result.setdefault("reference_video_urls", videos)
            return result

        # Seedance 1.5 uses input_urls rather than the 2.x reference arrays.
        if images and "input_urls" in fields:
            result.setdefault("input_urls", images)
        return result

    @staticmethod
    def adapt_references(
        generation: Generation,
        target: ModelSpec,
        parameters: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        result = dict(parameters)
        images, videos = GenerationActionService.parent_references(generation)
        fields = set(target.known_fields)

        if target.family == "seedance":
            result = GenerationActionService._adapt_seedance_references(
                generation,
                target,
                result,
                images,
                videos,
            )
            input_url = generation.input_url or (images[0] if images else None)
            return result, input_url

        if images:
            if "image_urls" in fields:
                result.setdefault("image_urls", images)
            if "input_urls" in fields:
                result.setdefault("input_urls", images)
            if "image_input" in fields:
                result.setdefault("image_input", images)
            if "reference_image_urls" in fields:
                result.setdefault("reference_image_urls", images)
            for name in ("image_url", "first_frame_url", "first_frame", "reference_image"):
                if name in fields:
                    result.setdefault(name, images[0])

        if videos:
            if "video_urls" in fields:
                result.setdefault("video_urls", videos)
            if "reference_video_urls" in fields:
                result.setdefault("reference_video_urls", videos)
            for name in ("video_url", "first_clip_url", "reference_video"):
                if name in fields:
                    result.setdefault(name, videos[0])

        input_url = generation.input_url or (images[0] if images else None)
        return result, input_url

    @staticmethod
    def edit_prompt(instruction: str, edit_kind: str | None) -> str:
        detail = instruction.strip()
        kind = edit_kind if edit_kind in _EDIT_FOCUS else "custom"
        focus = _EDIT_FOCUS[kind]
        return (
            f"Edit the reference image. Change ONLY {focus} to: {detail}. "
            "Keep the person's identity, face, body, pose, composition, camera, lighting, "
            "background and every unrelated detail unchanged unless the requested focus is the background."
        )
