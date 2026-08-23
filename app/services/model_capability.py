"""Model capability resolver.

Single backend-side oracle answering "which models can do X with input Y".
Reads only :mod:`app.services.model_catalog` (the single source of truth for
model configuration) and never duplicates model ids or pricing. Action
resolvers and ``GenerationActionService`` delegate mode/input compatibility
checks here instead of re-implementing them.
"""

from __future__ import annotations

from app.services.model_catalog import ModelCatalog, ModelSpec, UnknownModelError

IMAGE_INPUT_FIELDS = frozenset(
    {
        "image_urls",
        "input_urls",
        "image_input",
        "image_url",
        "first_frame_url",
        "first_frame",
        "reference_image",
        "reference_image_urls",
    }
)

VIDEO_INPUT_FIELDS = frozenset(
    {
        "video_urls",
        "video_url",
        "first_clip_url",
        "reference_video",
        "reference_video_urls",
    }
)

AUDIO_INPUT_FIELDS = frozenset({"audio_ids", "reference_audio_urls"})

# Operations that accept an image and edit/regenerate it.
IMAGE_EDIT_OPERATIONS = frozenset({"image_edit", "image_to_image", "generate_or_edit"})

# Operations that produce video conditioned on an image (i2v family).
VIDEO_I2V_OPERATIONS = frozenset(
    {"image_to_video", "text_or_image_to_video", "multimodal_video", "reference_to_video"}
)

# Operations that consume a video as the primary source (edit/extend/upscale).
_VIDEO_CONSUMING_OPERATIONS = frozenset(
    {"motion_control", "video_edit", "video_upscale", "video_extend"}
)

# Canonical generation modes used across action contexts.
MODE_TEXT_TO_IMAGE = "text_to_image"
MODE_IMAGE_TO_IMAGE = "image_to_image"
MODE_TEXT_TO_VIDEO = "text_to_video"
MODE_IMAGE_TO_VIDEO = "image_to_video"

_MODE_OPERATIONS: dict[str, frozenset[str]] = {
    MODE_TEXT_TO_IMAGE: frozenset({"text_to_image", *IMAGE_EDIT_OPERATIONS}),
    MODE_IMAGE_TO_IMAGE: IMAGE_EDIT_OPERATIONS,
    MODE_TEXT_TO_VIDEO: frozenset(
        {"text_to_video", "text_or_image_to_video", "multimodal_video", "reference_to_video"}
    ),
    MODE_IMAGE_TO_VIDEO: VIDEO_I2V_OPERATIONS,
}


class ModelCapabilityResolver:
    """Answers capability questions strictly from the live ModelCatalog."""

    @staticmethod
    def supports(spec: ModelSpec, mode: str) -> bool:
        """True when ``spec`` can generate in canonical ``mode``."""
        operations = _MODE_OPERATIONS.get(mode)
        if operations is None:
            # Unknown canonical modes fall back to a direct operation match.
            return spec.operation == mode
        return spec.operation in operations

    @staticmethod
    def supports_input(spec: ModelSpec, input_type: str) -> bool:
        """True when ``spec`` declares fields accepting the given input media."""
        fields = {
            "image": IMAGE_INPUT_FIELDS,
            "video": VIDEO_INPUT_FIELDS,
            "audio": AUDIO_INPUT_FIELDS,
        }.get(input_type)
        if fields is None:
            return False
        return bool(set(spec.known_fields) & fields)

    @staticmethod
    def consumes_source_media(spec: ModelSpec) -> bool:
        """True for transform-style ops that must not be picked as fallbacks."""
        return spec.operation in _VIDEO_CONSUMING_OPERATIONS

    @classmethod
    def compatible_specs(cls, result_media_type: str, mode: str) -> list[ModelSpec]:
        """All catalog specs able to run ``mode`` given the source result type.

        ``result_media_type`` is the media type of the generation the user wants
        to act upon. Image-consuming modes (i2i / i2v) require an image source;
        plain t2* modes only require matching output media type.
        """
        if not result_media_type:
            return []

        def eligible(spec: ModelSpec) -> bool:
            if not cls.supports(spec, mode):
                return False
            if mode in {MODE_IMAGE_TO_IMAGE, MODE_IMAGE_TO_VIDEO}:
                if result_media_type != "image":
                    return False
                expected_output = "image" if mode == MODE_IMAGE_TO_IMAGE else "video"
                return spec.media_type == expected_output and cls.supports_input(spec, "image")
            if mode == MODE_TEXT_TO_IMAGE:
                return spec.media_type == "image"
            if mode == MODE_TEXT_TO_VIDEO:
                return spec.media_type == "video"
            return True

        specs = [ModelCatalog.get(str(item["id"])) for item in ModelCatalog.list()]
        return [spec for spec in specs if eligible(spec)]

    @classmethod
    def resolve_fallback(cls, result_media_type: str, mode: str) -> ModelSpec | None:
        """Deterministic default model for ``mode``; None when nothing fits.

        Preference order: any compatible spec whose operation exactly matches
        the requested mode, then broader multimodal operations. Transform-only
        operations (upscale/extend/motion control) are never chosen.
        """
        candidates = [
            spec
            for spec in cls.compatible_specs(result_media_type, mode)
            if not cls.consumes_source_media(spec)
        ]
        if not candidates:
            return None
        exact_operation = {
            MODE_TEXT_TO_IMAGE: "text_to_image",
            MODE_IMAGE_TO_IMAGE: "image_edit",
            MODE_IMAGE_TO_VIDEO: "image_to_video",
        }.get(mode)
        if exact_operation:
            exact = next((spec for spec in candidates if spec.operation == exact_operation), None)
            if exact is not None:
                return exact
        return candidates[0]

    @classmethod
    def spec_family(cls, model_id: str) -> str:
        try:
            return ModelCatalog.get(model_id).family
        except UnknownModelError:
            return ""
