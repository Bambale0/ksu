from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import AdminTrend
from app.db.models import Generation
from app.services.credits import InternalCreditService
from app.services.generations import GenerationService
from app.services.model_catalog import ModelCatalog, ModelSpec
from app.services.model_ui_contract import MODEL_DEFAULTS, MODEL_FIELD_SUGGESTIONS
from app.services.seedance_reference_integrity import seedance_reference_requirements
from app.services.trend_collections import TrendCollectionService
from app.services.trend_user_fields import (
    TrendUserFieldsError,
    normalize_trend_user_fields,
    render_trend_prompt,
)

logger = logging.getLogger(__name__)

_REFERENCE_LIST_FIELDS = (
    "reference_image_urls",
    "image_input",
    "image_urls",
    "input_urls",
)
_REFERENCE_SINGLE_FIELDS = (
    "image_url",
    "first_frame_url",
    "first_frame",
)
_VIDEO_REFERENCE_FIELDS = (
    "reference_video_urls",
    "video_urls",
    "video_url",
    "reference_video",
    "first_clip_url",
)
_AUDIO_REFERENCE_FIELDS = (
    "reference_audio_urls",
    "audio_urls",
    "audio_url",
    "reference_audio",
)


class TrendRecipeError(ValueError):
    pass


class TrendService:
    """Server-owned curated trend templates and one-tap generation orchestration."""

    @staticmethod
    def normalize_recipe(title: str, payload: dict[str, Any]) -> dict[str, Any]:
        clean_title = str(title or "").strip()
        if not clean_title or len(clean_title) > 80:
            raise TrendRecipeError("Trend title must contain 1..80 characters")
        description = str(payload.get("description") or "").strip()
        if len(description) > 240:
            raise TrendRecipeError("Trend description must be at most 240 characters")
        model_id = str(payload.get("model_id") or payload.get("model") or "").strip()
        if not model_id:
            raise TrendRecipeError("model_id is required")
        spec = ModelCatalog.get(model_id)
        prompt = str(payload.get("prompt") or payload.get("prompt_text") or "").strip()
        if not prompt or len(prompt) > 8000:
            raise TrendRecipeError("Hidden trend prompt must contain 1..8000 characters")
        try:
            user_fields = normalize_trend_user_fields(payload.get("user_fields"), prompt=prompt)
        except TrendUserFieldsError as exc:
            raise TrendRecipeError(str(exc)) from exc
        preview_url = TrendService._safe_http_url(payload.get("preview_url"), field="preview_url")
        media_type = str(payload.get("media_type") or spec.media_type).strip().lower()
        if media_type not in {"image", "video"} or media_type != spec.media_type:
            raise TrendRecipeError("media_type must match the selected model")
        parameters = payload.get("parameters")
        if parameters is None:
            parameters = payload.get("generation_settings") or {}
        if not isinstance(parameters, dict):
            raise TrendRecipeError("parameters must be an object")
        parameters = dict(parameters)
        for key in ("model", "model_id", "kind", "user_input", "count"):
            parameters.pop(key, None)
        raw_input_mode = payload.get("input_mode") or payload.get("user_input") or "none"
        input_mode = str(raw_input_mode).strip().lower()
        if input_mode in {"photo", "image", "reference", "references"}:
            input_mode = "image"
        elif input_mode in {"none", "text", "prompt"}:
            input_mode = "none"
        elif input_mode != "multimodal":
            raise TrendRecipeError("input_mode must be 'none', 'image' or 'multimodal'")

        typed_slots = (
            seedance_reference_requirements(prompt)
            if spec.family == "seedance"
            else {"image": 0, "video": 0, "audio": 0}
        )
        if any(typed_slots.values()):
            input_mode = "multimodal"
            reference_requirements = {
                kind: {"min": count, "max": count}
                for kind, count in typed_slots.items()
            }
            min_references = sum(typed_slots.values())
            max_references = min_references
        else:
            reference_field = TrendService._reference_field(spec)
            default_max = 1 if reference_field in _REFERENCE_SINGLE_FIELDS else 8
            min_references = int(payload.get("min_references", 1 if input_mode == "image" else 0))
            max_references = int(payload.get("max_references", default_max if input_mode == "image" else 0))
            if min_references < 0 or max_references < min_references or max_references > 16:
                raise TrendRecipeError("Reference limits are invalid")
            if input_mode == "none" and (min_references or max_references):
                raise TrendRecipeError("Reference limits require input_mode='image'")
            if input_mode == "image" and reference_field is None:
                raise TrendRecipeError("Selected model does not accept image references")
            if reference_field in _REFERENCE_SINGLE_FIELDS and max_references > 1:
                raise TrendRecipeError("Selected model accepts only one reference image")
            reference_requirements = {
                "image": {
                    "min": min_references if input_mode == "image" else 0,
                    "max": max_references if input_mode == "image" else 0,
                },
                "video": {"min": 0, "max": 0},
                "audio": {"min": 0, "max": 0},
            }
        billing_seconds_raw = payload.get("billing_seconds")
        if billing_seconds_raw is None and spec.duration_field:
            billing_seconds_raw = parameters.get(spec.duration_field)
        billing_seconds = int(billing_seconds_raw) if billing_seconds_raw not in (None, "") else None
        if billing_seconds is not None and billing_seconds <= 0:
            raise TrendRecipeError("billing_seconds must be positive")
        if (
            billing_seconds is not None
            and spec.duration_field
            and spec.duration_field in spec.required_fields
            and parameters.get(spec.duration_field) in (None, "")
        ):
            parameters[spec.duration_field] = billing_seconds
        tags = payload.get("tags") or []
        if not isinstance(tags, list):
            raise TrendRecipeError("tags must be an array")
        clean_tags = []
        for item in tags[:20]:
            value = str(item).strip().lower()
            if value and len(value) <= 40 and value not in clean_tags:
                clean_tags.append(value)
        sort_order = int(payload.get("sort_order", 0))
        if sort_order < -100_000 or sort_order > 100_000:
            raise TrendRecipeError("sort_order is out of range")
        usage_count = max(0, int(payload.get("usage_count", 0)))
        return {
            "schema_version": 1,
            "description": description,
            "media_type": media_type,
            "preview_url": preview_url,
            "model_id": spec.id,
            "prompt": prompt,
            "user_fields": user_fields,
            "parameters": parameters,
            "billing_seconds": billing_seconds,
            "input_mode": input_mode,
            "min_references": min_references,
            "max_references": max_references,
            "reference_requirements": reference_requirements,
            "tags": clean_tags,
            "sort_order": sort_order,
            "usage_count": usage_count,
        }

    @staticmethod
    async def validate_recipe(session: AsyncSession, *, title: str, payload: dict[str, Any]) -> dict[str, Any]:
        recipe = TrendService.normalize_recipe(title, payload)
        reference_media = TrendService._synthetic_reference_media(recipe)
        parameters = TrendService._parameters_with_reference_media(recipe, **reference_media)
        try:
            await GenerationService.prepare_template_request(
                session,
                model_id=recipe["model_id"],
                prompt=recipe["prompt"],
                parameters=parameters,
                billing_seconds=recipe["billing_seconds"],
            )
        except ValueError as exc:
            raise TrendRecipeError(f"Trend generation recipe is invalid: {exc}") from exc
        return recipe

    @staticmethod
    def admin_view(item: AdminTrend) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "title": item.title,
            "payload": item.payload,
            "is_active": item.is_active,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }

    @staticmethod
    async def list_public(
        session: AsyncSession,
        *,
        limit: int = 50,
        media_type: str | None = None,
    ) -> dict[str, Any]:
        collection_state = await TrendCollectionService.state(session)
        rows = list(
            (
                await session.scalars(
                    select(AdminTrend)
                    .where(AdminTrend.is_active.is_(True))
                    .order_by(AdminTrend.created_at.desc())
                )
            ).all()
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            if (
                TrendCollectionService.assigned_collection(collection_state, row.id)
                != TrendCollectionService.DEFAULT_COLLECTION_ID
            ):
                continue
            try:
                view = await TrendService.public_view(session, row)
            except (ValueError, KeyError):
                continue
            if media_type and view["media_type"] != media_type:
                continue
            items.append(view)
        items.sort(key=lambda item: (int(item["sort_order"]), item["created_at"]), reverse=True)
        return {"items": items[: max(1, min(limit, 100))]}

    @staticmethod
    async def get_public(session: AsyncSession, *, trend_id: uuid.UUID) -> dict[str, Any]:
        item = await session.get(AdminTrend, trend_id)
        if item is None or not item.is_active:
            raise LookupError("Trend not found")
        try:
            return await TrendService.public_view(session, item)
        except (ValueError, KeyError) as exc:
            raise LookupError("Trend not found") from exc

    @staticmethod
    async def public_view(session: AsyncSession, item: AdminTrend) -> dict[str, Any]:
        recipe = TrendService.normalize_recipe(item.title, item.payload or {})
        reference_media = TrendService._synthetic_reference_media(recipe)
        parameters = TrendService._parameters_with_reference_media(recipe, **reference_media)
        spec, _clean, cost, seconds, _unit = await GenerationService.prepare_template_request(
            session,
            model_id=recipe["model_id"],
            prompt=recipe["prompt"],
            parameters=parameters,
            billing_seconds=recipe["billing_seconds"],
        )
        return {
            "id": str(item.id),
            "title": item.title,
            "description": recipe["description"],
            "media_type": recipe["media_type"],
            "preview_url": recipe["preview_url"],
            "model": {"id": spec.id, "title": spec.title, "family": spec.family},
            "cost_credits": TrendService._amount(cost),
            "cost_rub": TrendService._amount(InternalCreditService.rubles_for(cost)),
            "billing_seconds": seconds,
            "reference_requirements": TrendService._public_reference_requirements(recipe),
            "user_fields": recipe["user_fields"],
            "tags": recipe["tags"],
            "usage_count": recipe["usage_count"],
            "sort_order": recipe["sort_order"],
            "prompt_hidden": True,
            "prompt_actions_allowed": False,
            "created_at": item.created_at.isoformat(),
            **(
                {"quality_options": await TrendService._quality_options(session, recipe, reference_media)}
                if TrendService._resolution_options(recipe)
                else {}
            ),
        }

    @staticmethod
    async def run(
        session: AsyncSession,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        trend_id: uuid.UUID,
        reference_urls: list[str],
        image_reference_urls: list[str] | None = None,
        video_reference_urls: list[str] | None = None,
        audio_reference_urls: list[str] | None = None,
        user_values: dict[str, str] | None = None,
        resolution: str | None = None,
    ) -> tuple[Generation, dict[str, Any]]:
        item = await session.get(AdminTrend, trend_id)
        if item is None or not item.is_active:
            raise LookupError("Trend not found")
        recipe = TrendService.normalize_recipe(item.title, item.payload or {})
        raw_images = reference_urls if image_reference_urls is None else image_reference_urls
        images = [
            TrendService._safe_http_url(url, field="image_reference_url")
            for url in raw_images
        ]
        videos = [
            TrendService._safe_http_url(url, field="video_reference_url")
            for url in (video_reference_urls or [])
        ]
        audios = [
            TrendService._safe_http_url(url, field="audio_reference_url")
            for url in (audio_reference_urls or [])
        ]
        TrendService._validate_reference_media(
            recipe,
            image_reference_urls=images,
            video_reference_urls=videos,
            audio_reference_urls=audios,
        )
        parameters = TrendService._parameters_with_reference_media(
            recipe,
            image_reference_urls=images,
            video_reference_urls=videos,
            audio_reference_urls=audios,
            resolution=resolution,
        )
        try:
            rendered_prompt = render_trend_prompt(recipe["prompt"], recipe["user_fields"], user_values)
        except TrendUserFieldsError as exc:
            raise TrendRecipeError(str(exc)) from exc
        generation = await GenerationService.create(
            session,
            redis,
            user_id=user_id,
            model_id=recipe["model_id"],
            prompt=rendered_prompt,
            parameters=parameters,
            billing_seconds=recipe["billing_seconds"],
            action_type="trend",
        )
        try:
            locked = await session.scalar(select(AdminTrend).where(AdminTrend.id == trend_id).with_for_update())
            if locked is not None:
                payload = dict(locked.payload or {})
                payload["usage_count"] = max(0, int(payload.get("usage_count", 0))) + 1
                locked.payload = payload
                await session.commit()
        except Exception:
            await session.rollback()
            logger.warning("Trend usage analytics failed for %s", trend_id, exc_info=True)
        return generation, {
            "trend_id": str(trend_id),
            "prompt_hidden": True,
            "prompt_actions_allowed": False,
            "model": {"id": recipe["model_id"], "title": ModelCatalog.get(recipe["model_id"]).title},
        }

    @staticmethod
    def _reference_requirement(recipe: dict[str, Any], kind: str) -> tuple[int, int]:
        requirements = recipe.get("reference_requirements")
        if isinstance(requirements, dict):
            value = requirements.get(kind)
            if isinstance(value, dict):
                minimum = max(0, int(value.get("min", 0)))
                maximum = max(minimum, int(value.get("max", minimum)))
                return minimum, maximum
        if kind == "image" and recipe.get("input_mode") == "image":
            minimum = max(0, int(recipe.get("min_references", 0)))
            maximum = max(minimum, int(recipe.get("max_references", minimum)))
            return minimum, maximum
        return 0, 0

    @staticmethod
    def _public_reference_requirements(recipe: dict[str, Any]) -> dict[str, Any]:
        typed = {
            kind: {"min": minimum, "max": maximum}
            for kind in ("image", "video", "audio")
            for minimum, maximum in [TrendService._reference_requirement(recipe, kind)]
        }
        total_min = sum(value["min"] for value in typed.values())
        total_max = sum(value["max"] for value in typed.values())
        active = [kind for kind, value in typed.items() if value["max"] > 0]
        kind = active[0] if len(active) == 1 else ("multimodal" if active else "none")
        return {
            "kind": kind,
            "min": total_min,
            "max": total_max,
            **typed,
        }

    @staticmethod
    def _synthetic_reference_media(recipe: dict[str, Any]) -> dict[str, list[str]]:
        counts = {
            kind: TrendService._reference_requirement(recipe, kind)[0]
            for kind in ("image", "video", "audio")
        }
        return {
            "image_reference_urls": [
                f"https://example.invalid/trend-image-{index + 1}.jpg"
                for index in range(counts["image"])
            ],
            "video_reference_urls": [
                f"https://example.invalid/trend-video-{index + 1}.mp4"
                for index in range(counts["video"])
            ],
            "audio_reference_urls": [
                f"https://example.invalid/trend-audio-{index + 1}.mp3"
                for index in range(counts["audio"])
            ],
        }

    @staticmethod
    def _validate_reference_media(
        recipe: dict[str, Any],
        *,
        image_reference_urls: list[str],
        video_reference_urls: list[str],
        audio_reference_urls: list[str],
    ) -> None:
        values = {
            "image": (image_reference_urls, "фото"),
            "video": (video_reference_urls, "видео"),
            "audio": (audio_reference_urls, "аудио"),
        }
        for kind, (items, label) in values.items():
            minimum, maximum = TrendService._reference_requirement(recipe, kind)
            count = len(items)
            if count < minimum or count > maximum:
                if minimum == maximum:
                    raise TrendRecipeError(
                        f"Тренд требует {minimum} {label}-референсов, получено {count}"
                    )
                raise TrendRecipeError(
                    f"Тренд требует от {minimum} до {maximum} {label}-референсов, получено {count}"
                )

    @staticmethod
    def _parameters_with_reference_media(
        recipe: dict[str, Any],
        *,
        image_reference_urls: list[str],
        video_reference_urls: list[str],
        audio_reference_urls: list[str],
        resolution: str | None = None,
    ) -> dict[str, Any]:
        parameters = dict(recipe.get("parameters") or {})
        TrendService._apply_resolution_override(recipe, parameters, resolution=resolution)
        spec = ModelCatalog.get(str(recipe["model_id"]))
        for field in (
            *_REFERENCE_LIST_FIELDS,
            *_REFERENCE_SINGLE_FIELDS,
            *_VIDEO_REFERENCE_FIELDS,
            *_AUDIO_REFERENCE_FIELDS,
        ):
            parameters.pop(field, None)

        if spec.family == "seedance":
            if image_reference_urls:
                parameters["reference_image_urls"] = image_reference_urls
            if video_reference_urls:
                parameters["reference_video_urls"] = video_reference_urls
            if audio_reference_urls:
                parameters["reference_audio_urls"] = audio_reference_urls
            return parameters

        if spec.id == "wan-2.7-r2v":
            if audio_reference_urls:
                raise TrendRecipeError("WAN R2V does not accept audio references")
            if image_reference_urls:
                parameters["reference_image"] = image_reference_urls
            if video_reference_urls:
                parameters["reference_video"] = video_reference_urls
            return parameters

        if video_reference_urls or audio_reference_urls:
            raise TrendRecipeError("Selected model does not accept video/audio references")
        if not image_reference_urls:
            return parameters
        field = TrendService._reference_field(spec)
        if field is None:
            raise TrendRecipeError("Selected model does not accept image references")
        if field in _REFERENCE_SINGLE_FIELDS and len(image_reference_urls) != 1:
            raise TrendRecipeError("Selected model requires exactly one reference image")
        parameters[field] = (
            image_reference_urls if field in _REFERENCE_LIST_FIELDS else image_reference_urls[0]
        )
        return parameters

    @staticmethod
    def _parameters_with_references(
        recipe: dict[str, Any],
        reference_urls: list[str],
        *,
        resolution: str | None = None,
    ) -> dict[str, Any]:
        return TrendService._parameters_with_reference_media(
            recipe,
            image_reference_urls=reference_urls,
            video_reference_urls=[],
            audio_reference_urls=[],
            resolution=resolution,
        )

    @staticmethod
    def _resolution_options(recipe: dict[str, Any]) -> list[str]:
        if recipe.get("media_type") != "video":
            return []
        model_id = str(recipe["model_id"])
        spec = ModelCatalog.get(model_id)
        if "resolution" not in set(spec.known_fields):
            return []
        suggestions = MODEL_FIELD_SUGGESTIONS.get(model_id, {}).get("resolution") or []
        options: list[str] = []
        current = TrendService._default_resolution(recipe)
        for item in suggestions:
            value = str(item).strip()
            if value and value not in options:
                options.append(value)
        if current and current not in options:
            options.insert(0, current)
        return options

    @staticmethod
    def _default_resolution(recipe: dict[str, Any]) -> str | None:
        parameters = recipe.get("parameters") if isinstance(recipe.get("parameters"), dict) else {}
        current = str(parameters.get("resolution") or "").strip()
        if current:
            return current
        default = MODEL_DEFAULTS.get(str(recipe["model_id"]), {}).get("resolution")
        return str(default).strip() if default else None

    @staticmethod
    def _apply_resolution_override(
        recipe: dict[str, Any],
        parameters: dict[str, Any],
        *,
        resolution: str | None,
    ) -> None:
        if resolution in (None, ""):
            return
        selected = str(resolution).strip()
        options = TrendService._resolution_options(recipe)
        if not options:
            raise TrendRecipeError("This trend does not support video quality selection")
        if selected not in options:
            raise TrendRecipeError("Unsupported video quality")
        parameters["resolution"] = selected

    @staticmethod
    async def _quality_options(
        session: AsyncSession,
        recipe: dict[str, Any],
        reference_media: dict[str, list[str]],
    ) -> list[dict[str, Any]]:
        options = TrendService._resolution_options(recipe)
        default = TrendService._default_resolution(recipe) or (options[0] if options else None)
        result: list[dict[str, Any]] = []
        for resolution in options:
            parameters = TrendService._parameters_with_reference_media(
                recipe,
                image_reference_urls=reference_media["image_reference_urls"],
                video_reference_urls=reference_media["video_reference_urls"],
                audio_reference_urls=reference_media["audio_reference_urls"],
                resolution=resolution,
            )
            _spec, _clean, cost, seconds, _unit = await GenerationService.prepare_template_request(
                session,
                model_id=recipe["model_id"],
                prompt=recipe["prompt"],
                parameters=parameters,
                billing_seconds=recipe["billing_seconds"],
            )
            result.append(
                {
                    "value": resolution,
                    "label": resolution,
                    "cost_credits": TrendService._amount(cost),
                    "cost_rox": TrendService._amount(cost),
                    "cost_rub": TrendService._amount(InternalCreditService.rubles_for(cost)),
                    "billing_seconds": seconds,
                    "default": resolution == default,
                }
            )
        return result

    @staticmethod
    def _reference_field(spec: ModelSpec) -> str | None:
        known = set(spec.known_fields)
        for field in (*_REFERENCE_LIST_FIELDS, *_REFERENCE_SINGLE_FIELDS):
            if field in known:
                return field
        return None

    @staticmethod
    def _safe_http_url(value: Any, *, field: str) -> str:
        url = str(value or "").strip()
        if not url or len(url) > 4000:
            raise TrendRecipeError(f"{field} must be a valid HTTP(S) URL")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise TrendRecipeError(f"{field} must be a valid HTTP(S) URL")
        return url

    @staticmethod
    def _amount(value: Decimal | str | int | float) -> str:
        return format(Decimal(str(value)), ".2f")
