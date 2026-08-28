from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.feed_models import FeedRemixEvent
from app.db.models import Generation
from app.services.billing_access import BillingAccessService
from app.services.feed import FeedError, FeedService
from app.services.generations import GenerationService
from app.services.model_catalog import ModelCatalog, UnknownModelError
from app.services.model_routing import REFERENCE_PARAMETER_FIELDS
from app.services.reference_resolver import ReferenceResolver
from app.services.references import ReferenceService


AUDIO_REFERENCE_FIELDS = frozenset(
    {
        "audio_url",
        "audio_urls",
        "reference_audio",
        "reference_audio_url",
        "reference_audio_urls",
    }
)
REFERENCE_FIELDS = frozenset(REFERENCE_PARAMETER_FIELDS) | AUDIO_REFERENCE_FIELDS | frozenset(
    {"last_frame", "input_video_url"}
)


class FeedRemixReferenceError(FeedError):
    pass


class FeedRemixService:
    """Server-owned feed repeat flow.

    Feed publications contribute the model, prompt and non-reference settings.
    Reference media is never inherited from the author. A remix only starts after
    the current user explicitly supplies references owned by their ROXY account.
    Hidden prompts remain server-side throughout the flow.
    """

    @staticmethod
    def _source_model_ids(source: Generation) -> tuple[str, str]:
        parameters = dict(source.parameters or {})
        effective_model_id = str(parameters.get("_model_id") or "").strip()
        requested_model_id = str(parameters.get("_requested_model_id") or effective_model_id).strip()
        if not effective_model_id:
            raise FeedError("Source model is not reusable")
        try:
            ModelCatalog.get(effective_model_id)
            ModelCatalog.get(requested_model_id)
        except UnknownModelError as exc:
            raise FeedError("Source model is no longer available") from exc
        return requested_model_id, effective_model_id

    @staticmethod
    def _reusable_parameters(source: Generation, effective_model_id: str) -> dict[str, Any]:
        spec = ModelCatalog.get(effective_model_id)
        allowed = set(spec.known_fields)
        return {
            key: value
            for key, value in dict(source.parameters or {}).items()
            if not key.startswith("_")
            and key != "prompt"
            and key in allowed
            and key not in REFERENCE_FIELDS
        }

    @staticmethod
    def _audio_references(parameters: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for field in AUDIO_REFERENCE_FIELDS:
            raw = parameters.get(field)
            if isinstance(raw, (list, tuple)):
                values.extend(str(item) for item in raw if item)
            elif raw:
                values.append(str(raw))
        return list(dict.fromkeys(values))

    @classmethod
    def _reference_requirements(cls, source: Generation) -> dict[str, int | bool]:
        context = ReferenceResolver.generation_context(source)
        audio_references = cls._audio_references(context.parameters)
        image_count = len(context.reference_images)
        video_count = len(context.reference_videos)
        audio_count = len(audio_references)
        return {
            "image_count": image_count,
            "video_count": video_count,
            "audio_count": audio_count,
            "required": bool(image_count or video_count or audio_count),
        }

    @staticmethod
    def _root_source_id(source: Generation) -> uuid.UUID:
        return source.source_feed_gen_id or source.id

    @classmethod
    async def prepare(
        cls,
        session: AsyncSession,
        *,
        source_generation_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        surface: str,
    ) -> dict[str, Any]:
        source = await FeedService.assert_surface_visible(
            session,
            source_generation_id,
            surface=surface,
        )
        if source.action_type == "trend":
            raise FeedError("Trend generations cannot be remixed")

        requested_model_id, effective_model_id = cls._source_model_ids(source)
        card = await FeedService.to_card(
            session,
            source,
            viewer_user_id=viewer_user_id,
            surface=surface,
        )
        prompt_hidden = bool(card.get("prompt_hidden"))
        return {
            "source_generation_id": str(source.id),
            "source_feed_gen_id": str(cls._root_source_id(source)),
            "surface": surface,
            "model_id": requested_model_id,
            "effective_model_id": effective_model_id,
            "model_title": ModelCatalog.get(effective_model_id).title,
            "prompt": "" if prompt_hidden else source.prompt,
            "prompt_hidden": prompt_hidden,
            "prompt_editable": not prompt_hidden,
            "settings": cls._reusable_parameters(source, effective_model_id),
            "billing_seconds": (source.parameters or {}).get("_billing_seconds"),
            "reference_requirements": cls._reference_requirements(source),
            "preview_url": card.get("preview_url") or card.get("result_url"),
            "media": card.get("media") or [],
        }

    @classmethod
    async def _owned_reference_urls(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        reference_ids: list[uuid.UUID],
    ) -> dict[str, list[str]]:
        try:
            rows = await ReferenceService.resolve_owned(
                session,
                user_id=user_id,
                reference_ids=reference_ids,
            )
        except LookupError as exc:
            raise FeedRemixReferenceError("One or more references are unavailable") from exc

        by_kind: dict[str, list[str]] = {"image": [], "video": [], "audio": []}
        for row in rows:
            if row.kind in by_kind:
                by_kind[row.kind].append(row.source_url)
        return by_kind

    @staticmethod
    def _assert_reference_requirements(
        requirements: dict[str, int | bool],
        references: dict[str, list[str]],
    ) -> None:
        labels = {"image": "image", "video": "video", "audio": "audio"}
        missing: list[str] = []
        for kind in ("image", "video", "audio"):
            expected = int(requirements.get(f"{kind}_count") or 0)
            supplied = len(references.get(kind) or [])
            if supplied < expected:
                missing.append(f"{expected} {labels[kind]} reference(s)")
        if missing:
            raise FeedRemixReferenceError(
                "Add your own references before repeating: " + ", ".join(missing)
            )

    @staticmethod
    def _parameters_with_owned_references(
        base: dict[str, Any],
        references: dict[str, list[str]],
    ) -> dict[str, Any]:
        parameters = dict(base)
        images = references.get("image") or []
        videos = references.get("video") or []
        audios = references.get("audio") or []
        if images:
            parameters["reference_images"] = images
        if videos:
            parameters["reference_videos"] = videos
        if audios:
            parameters["reference_audio_urls"] = audios
        return parameters

    @classmethod
    async def _composition(
        cls,
        session: AsyncSession,
        *,
        source_generation_id: uuid.UUID,
        remix_author_id: uuid.UUID,
        surface: str,
        prompt_override: str | None,
        reference_ids: list[uuid.UUID],
        confirm_own_references: bool,
    ) -> tuple[Generation, str, str, dict[str, Any], int | None]:
        if not confirm_own_references:
            raise FeedRemixReferenceError("Confirm your own references before repeating")

        source = await FeedService.assert_surface_visible(
            session,
            source_generation_id,
            surface=surface,
        )
        if source.action_type == "trend":
            raise FeedError("Trend generations cannot be remixed")

        requested_model_id, effective_model_id = cls._source_model_ids(source)
        requirements = cls._reference_requirements(source)
        references = await cls._owned_reference_urls(
            session,
            user_id=remix_author_id,
            reference_ids=reference_ids,
        )
        cls._assert_reference_requirements(requirements, references)

        base = cls._reusable_parameters(source, effective_model_id)
        parameters = cls._parameters_with_owned_references(base, references)
        prompt = source.prompt
        if source.feed_prompt_visible and source.source_feed_gen_id is None and prompt_override is not None:
            prompt = prompt_override.strip()
        billing_seconds = (source.parameters or {}).get("_billing_seconds")
        return source, requested_model_id, prompt, parameters, billing_seconds

    @classmethod
    async def quote(
        cls,
        session: AsyncSession,
        *,
        source_generation_id: uuid.UUID,
        remix_author_id: uuid.UUID,
        surface: str,
        prompt_override: str | None,
        reference_ids: list[uuid.UUID],
        confirm_own_references: bool,
    ) -> dict[str, Any]:
        _source, model_id, prompt, parameters, billing_seconds = await cls._composition(
            session,
            source_generation_id=source_generation_id,
            remix_author_id=remix_author_id,
            surface=surface,
            prompt_override=prompt_override,
            reference_ids=reference_ids,
            confirm_own_references=confirm_own_references,
        )
        spec, _clean, retail_cost, seconds, unit_price = await GenerationService.prepare_request(
            session,
            model_id=model_id,
            prompt=prompt,
            input_url=None,
            parameters=parameters,
            billing_seconds=billing_seconds,
        )
        billing = await BillingAccessService.decision(
            session,
            user_id=remix_author_id,
            retail_cost=retail_cost,
        )
        return {
            "model_id": spec.id,
            "cost_rox": format(billing.effective_cost, ".2f"),
            "retail_cost_rox": format(billing.retail_cost, ".2f"),
            "unit_price_rox": format(Decimal(unit_price), ".2f"),
            "billing_seconds": seconds,
            "admin_free": billing.admin_free,
        }

    @classmethod
    async def launch(
        cls,
        session: AsyncSession,
        redis: Redis,
        *,
        source_generation_id: uuid.UUID,
        remix_author_id: uuid.UUID,
        surface: str,
        prompt_override: str | None,
        reference_ids: list[uuid.UUID],
        confirm_own_references: bool,
    ) -> Generation:
        source, model_id, prompt, parameters, billing_seconds = await cls._composition(
            session,
            source_generation_id=source_generation_id,
            remix_author_id=remix_author_id,
            surface=surface,
            prompt_override=prompt_override,
            reference_ids=reference_ids,
            confirm_own_references=confirm_own_references,
        )
        root_source_id = cls._root_source_id(source)
        generation = await GenerationService.create(
            session,
            redis,
            user_id=remix_author_id,
            model_id=model_id,
            prompt=prompt,
            input_url=None,
            parameters=parameters,
            billing_seconds=billing_seconds,
            source_feed_gen_id=root_source_id,
            parent_generation_id=source.id,
            action_type="remix",
        )
        session.add(
            FeedRemixEvent(
                source_generation_id=source.id,
                remix_generation_id=generation.id,
                source_author_id=source.user_id,
                remix_author_id=remix_author_id,
                credits_spent=Decimal(generation.cost_rox),
            )
        )
        await session.commit()
        return generation
