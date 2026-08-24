from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.models import Generation
from app.services.feed_static import FeedStaticStorage
from app.services.model_routing import (
    IMAGE_REFERENCE_FIELDS,
    VIDEO_REFERENCE_FIELDS,
    image_references,
    resolve_model_request,
    video_references,
)
from app.services.reference_static import ReferenceStaticStorage

EXPLICIT_MEDIA_INPUT_FIELDS = (
    "image_url",
    "image_urls",
    "image_input",
    "input_urls",
    "first_frame_url",
    "last_frame_url",
    "first_frame",
    "first_clip_url",
    "reference_image",
    "reference_image_urls",
    "video_url",
    "video_urls",
    "reference_video",
    "reference_video_urls",
)
PUBLIC_IMAGE_REFERENCE_FIELDS = tuple(dict.fromkeys((*IMAGE_REFERENCE_FIELDS, "last_frame")))
PUBLIC_VIDEO_REFERENCE_FIELDS = tuple(dict.fromkeys((*VIDEO_REFERENCE_FIELDS, "input_video_url")))


@dataclass(frozen=True, slots=True)
class GenerationContext:
    model_id: str
    prompt: str
    input_url: str | None
    parameters: dict[str, Any]
    provider_input: dict[str, Any]
    reference_images: list[str]
    reference_videos: list[str]


class ReferenceResolver:
    @staticmethod
    def _public_reference_url(value: str) -> bool:
        return (
            value.startswith("https://")
            or ReferenceStaticStorage.is_local_url(value)
            or FeedStaticStorage.is_local_url(value)
        )

    @staticmethod
    def _canonical_generation_parameters(
        parameters: dict[str, Any],
        input_url: str | None,
    ) -> dict[str, Any]:
        """Re-apply model routing before provider submit.

        Existing queued rows may contain old Mini App aliases such as
        ``input_video_urls`` or ``input_image_urls``. Creation-time validation is
        not enough for those rows: the worker builds the Kie payload from saved
        ``Generation.parameters``. Normalize again at the provider boundary so
        Seedance multi-reference requests reach Kie as canonical
        ``reference_*_urls`` arrays.
        """

        model_id = str(parameters.get("_model_id") or "").strip()
        if not model_id:
            return parameters

        private_parameters = {
            key: value
            for key, value in parameters.items()
            if key.startswith("_")
        }
        public_parameters = {
            key: value
            for key, value in parameters.items()
            if not key.startswith("_")
        }
        try:
            routed = resolve_model_request(
                model_id,
                public_parameters,
                input_url=input_url,
            )
        except Exception:
            return parameters
        return {**routed.parameters, **private_parameters}

    @classmethod
    def public_image_references(
        cls,
        parameters: dict[str, Any] | None,
        input_url: str | None = None,
    ) -> list[str]:
        return [
            value
            for value in image_references(dict(parameters or {}), input_url)
            if cls._public_reference_url(value)
        ]

    @classmethod
    def public_video_references(cls, parameters: dict[str, Any] | None) -> list[str]:
        return [
            value
            for value in video_references(dict(parameters or {}))
            if cls._public_reference_url(value)
        ]

    @staticmethod
    def provider_input(
        *,
        prompt: str,
        input_url: str | None,
        parameters: dict[str, Any] | None,
    ) -> dict[str, Any]:
        data = {
            key: value
            for key, value in dict(parameters or {}).items()
            if not key.startswith("_")
        }
        if prompt and not data.get("prompt"):
            data["prompt"] = prompt
        if input_url and not any(data.get(key) for key in EXPLICIT_MEDIA_INPUT_FIELDS):
            data["image_url"] = input_url
        return data

    @classmethod
    def generation_context(cls, generation: Generation) -> GenerationContext:
        raw_parameters = dict(generation.parameters or {})
        input_url = str(generation.input_url) if generation.input_url else None
        parameters = cls._canonical_generation_parameters(raw_parameters, input_url)
        prompt = str(generation.prompt or "")
        return GenerationContext(
            model_id=str(parameters.get("_model_id") or ""),
            prompt=prompt,
            input_url=input_url,
            parameters=parameters,
            provider_input=cls.provider_input(
                prompt=prompt,
                input_url=input_url,
                parameters=parameters,
            ),
            reference_images=cls.public_image_references(parameters, input_url),
            reference_videos=cls.public_video_references(parameters),
        )
