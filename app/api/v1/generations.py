from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select

from app.api.deps import CurrentUserDep, OptionalCurrentUserDep, RedisDep, SessionDep
from app.db.history_models import GenerationHistoryState
from app.db.models import Generation
from app.services.billing_access import BillingAccessService
from app.services.credits import InternalCreditService
from app.services.generations import MAX_GENERATION_QUANTITY, GenerationService
from app.services.media_assets import MediaAssetService
from app.services.model_family_catalog import build_model_families
from app.services.model_catalog import (
    InvalidModelParametersError,
    ModelCatalog,
    UnknownModelError,
)
from app.services.model_presentation import music_model_title, presentation_for, public_model_title
from app.services.model_ui_contract import build_public_model_ui_schema
from app.services.music_generation import (
    MAX_MUSIC_GENERATION_QUANTITY,
    MUSIC_MODEL_ID,
    MusicGenerationError,
    MusicGenerationService,
)
from app.services.object_storage import ObjectStorage, ObjectStorageNotConfigured
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/generations", tags=["generations"])

MAX_REQUEST_QUANTITY = min(MAX_GENERATION_QUANTITY, MAX_MUSIC_GENERATION_QUANTITY)


class CreateGenerationRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=100)
    prompt: str = Field(default="", max_length=8000)
    input_url: str | None = Field(default=None, max_length=4000)
    billing_seconds: int | None = Field(default=None, ge=1, le=600)
    parameters: dict[str, Any] = Field(default_factory=dict)
    quantity: int = Field(default=1, ge=1, le=MAX_REQUEST_QUANTITY)


def _amount(value: Decimal | str | int | float) -> str:
    return format(Decimal(str(value)), ".2f")


def _total(value: Decimal | str | int | float, quantity: int) -> Decimal:
    return (Decimal(str(value)) * Decimal(max(1, int(quantity)))).quantize(Decimal("0.01"))


def _public_catalog_unit_price(model_id: str, value: Decimal | str | int | float) -> Decimal:
    raw = Decimal(str(value))
    if model_id in ModelCatalog._pricing_overrides():
        return raw
    return InternalCreditService.legacy_credits_to_rox(raw)


def _model_view(generation: Generation) -> dict[str, str | None]:
    params = generation.parameters or {}
    model_id = str(params.get("_model_id") or "")
    provider_model = str(params.get("_provider_model") or params.get("_kie_model") or "") or None
    if MusicGenerationService.is_music_model(model_id):
        return {
            "id": MUSIC_MODEL_ID,
            "title": str(params.get("_model_title") or music_model_title(provider_model or "")),
            "family": str(params.get("_model_family") or "suno"),
            "operation": str(params.get("_operation") or "text_to_music"),
            "media_type": str(params.get("_media_type") or "audio"),
            "provider_model": provider_model,
        }
    try:
        spec = ModelCatalog.get(model_id)
    except UnknownModelError:
        return {
            "id": model_id or None,
            "title": str(params.get("_model_title") or model_id or "Unknown model"),
            "family": str(params.get("_model_family") or "") or None,
            "operation": str(params.get("_operation") or generation.kind),
            "media_type": str(params.get("_media_type") or "") or None,
            "provider_model": provider_model,
        }
    return {
        "id": spec.id,
        "title": public_model_title(spec.id, str(params.get("_model_title") or spec.title)),
        "family": str(params.get("_model_family") or spec.family),
        "operation": str(params.get("_operation") or spec.operation),
        "media_type": str(params.get("_media_type") or spec.media_type),
        "provider_model": provider_model or spec.kie_model,
    }


def _provider_result_urls(generation: Generation) -> list[str]:
    raw = (generation.parameters or {}).get("_result_urls")
    values = [str(item) for item in raw] if isinstance(raw, list) else []
    if generation.result_url and generation.result_url not in values:
        values.insert(0, generation.result_url)
    return values


def _public_settings(generation: Generation) -> dict[str, Any]:
    if generation.action_type == "trend":
        return {}
    params = dict(generation.parameters or {})
    model_id = str(params.get("_model_id") or "")
    if MusicGenerationService.is_music_model(model_id):
        return MusicGenerationService.public_settings(params)
    try:
        spec = ModelCatalog.get(model_id)
    except UnknownModelError:
        return {}
    allowed = set(spec.known_fields)
    return {
        key: value
        for key, value in params.items()
        if key in allowed and not key.startswith("_") and key != "prompt"
    }


def _generation_view(
    generation: Generation,
    *,
    hidden: bool = False,
    owned_media: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    cost = Decimal(generation.cost_rox)
    params = generation.parameters or {}
    retail_cost = Decimal(str(params.get("_retail_cost_rox") or cost))
    admin_free = bool(params.get("_admin_free"))
    owned_media = owned_media or []
    owned_urls = [str(item["url"]) for item in owned_media if item.get("url")]
    result_urls = owned_urls or _provider_result_urls(generation)
    trend_hidden = generation.action_type == "trend"
    model = _model_view(generation)
    view: dict[str, object] = {
        "id": str(generation.id),
        "status": generation.status,
        "prompt": "" if trend_hidden else generation.prompt,
        "model": model,
        "settings": _public_settings(generation),
        "prompt_hidden": trend_hidden,
        "prompt_actions_allowed": not trend_hidden,
        "cost_credits": _amount(cost),
        "cost_rox": _amount(cost),
        "cost_rub": _amount(InternalCreditService.rubles_for(cost)),
        "retail_cost_rox": _amount(retail_cost),
        "admin_free": admin_free,
        "billing_seconds": params.get("_billing_seconds"),
        "batch_id": params.get("_batch_id"),
        "batch_index": params.get("_batch_index"),
        "batch_size": params.get("_batch_size"),
        "result_url": result_urls[0] if result_urls else None,
        "result_urls": result_urls,
        "media": owned_media,
        "result_storage": "owned" if owned_urls else "provider",
        "error": generation.error,
        "hidden_from_history": hidden,
        "created_at": generation.created_at.isoformat(),
        "updated_at": generation.updated_at.isoformat(),
    }
    if model.get("media_type") == "audio":
        tracks = params.get("_music_tracks")
        view["music_tracks"] = tracks if isinstance(tracks, list) else []
    return view


async def _owned_media_views(
    session: SessionDep,
    *,
    user_id: uuid.UUID,
    generations: list[Generation],
) -> dict[uuid.UUID, list[dict[str, object]]]:
    assets = await MediaAssetService.ready_assets_for_generations(
        session,
        user_id=user_id,
        generation_ids=[item.id for item in generations],
    )
    if not assets:
        return {}
    try:
        storage = ObjectStorage()
    except ObjectStorageNotConfigured:
        return {}
    result: dict[uuid.UUID, list[dict[str, object]]] = {}
    for generation_id, rows in assets.items():
        result[generation_id] = [MediaAssetService.public_view(row, storage) for row in rows]
    return result


async def _owned_generation(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> Generation:
    generation = await session.get(Generation, generation_id)
    if generation is None or generation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    return generation


_SEEDANCE_REUSE_REFERENCE_FIELDS: tuple[str, ...] = (
    "reference_image_urls",
    "reference_video_urls",
    "reference_audio_urls",
    "first_frame_url",
    "last_frame_url",
    "input_urls",
)


def _recreate_payload_for_generation(generation: Generation) -> dict[str, object]:
    if generation.action_type == "trend":
        raise HTTPException(
            status_code=409,
            detail="Trend generations can only be repeated from the Trends catalog",
        )

    params = dict(generation.parameters or {})
    model_id = str(params.get("_model_id") or "")
    if not model_id:
        raise HTTPException(status_code=409, detail="Generation has no reusable model")
    if MusicGenerationService.is_music_model(model_id):
        return {
            "model_id": MUSIC_MODEL_ID,
            "prompt": generation.prompt,
            "input_url": None,
            "billing_seconds": None,
            "parameters": MusicGenerationService.reusable_parameters(params),
        }

    try:
        spec = ModelCatalog.get(model_id)
    except UnknownModelError as exc:
        raise HTTPException(status_code=409, detail="Generation model is no longer available") from exc

    allowed = set(spec.known_fields)
    clean = {
        key: value
        for key, value in params.items()
        if not key.startswith("_") and key in allowed and key != "prompt"
    }
    input_url = generation.input_url
    references_required = False
    if spec.family == "seedance":
        # Feed repeats must never silently reuse the parent's media inputs:
        # reference/frame URLs belong to the original author's upload session
        # and may be stale or broken. The user uploads their own references.
        references_required = any(
            clean.pop(name, None) for name in _SEEDANCE_REUSE_REFERENCE_FIELDS
        )
        input_url = None
    payload: dict[str, object] = {
        "model_id": model_id,
        "prompt": generation.prompt,
        "input_url": input_url,
        "billing_seconds": params.get("_billing_seconds"),
        "parameters": clean,
    }
    if references_required:
        payload["references_required"] = True
    return payload


@router.get("/models")
async def generation_models(
    user: OptionalCurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    admin_free = bool(user and await BillingAccessService.is_active_admin(session, user.id))
    models: list[dict[str, Any]] = []
    for item in ModelCatalog.list():
        enriched = dict(item)
        model_id = str(enriched["id"])
        presentation = presentation_for(enriched)
        enriched["title"] = str(presentation["title"] or enriched.get("title") or model_id)
        enriched["presentation"] = presentation
        unit_credits = enriched.get("price_rox")
        if unit_credits is not None:
            retail_unit = _public_catalog_unit_price(model_id, unit_credits)
            effective_unit = Decimal("0") if admin_free else retail_unit
            enriched["retail_price_rox"] = _amount(retail_unit)
            enriched["effective_price_rox"] = _amount(effective_unit)
            enriched["effective_price_credits"] = _amount(effective_unit)
            enriched["effective_price_rub"] = _amount(InternalCreditService.rubles_for(effective_unit))
            enriched["price_rox"] = _amount(retail_unit)
            enriched["price_credits"] = _amount(retail_unit)
            enriched["price_rub"] = _amount(InternalCreditService.rubles_for(retail_unit))
        enriched["admin_free"] = admin_free
        enriched["ui_schema"] = build_public_model_ui_schema(enriched)
        models.append(enriched)

    music = MusicGenerationService.public_model()
    music["title"] = music_model_title(str(music.get("kie_model") or ""))
    music_retail = Decimal(str(music.get("price_rox") or 0))
    music_effective = Decimal("0") if admin_free else music_retail
    music["retail_price_rox"] = _amount(music_retail)
    music["effective_price_rox"] = _amount(music_effective)
    music["effective_price_credits"] = _amount(music_effective)
    music["effective_price_rub"] = _amount(InternalCreditService.rubles_for(music_effective))
    music["price_rox"] = _amount(music_retail)
    music["price_credits"] = _amount(music_retail)
    music["price_rub"] = _amount(InternalCreditService.rubles_for(music_retail))
    music["admin_free"] = admin_free
    music["presentation"] = {
        "title": music["title"],
        "product_key": MUSIC_MODEL_ID,
        "product_title": music["title"],
        "family_group": None,
        "family_title": "Suno",
        "version_label": str(music.get("kie_model") or ""),
    }
    models.append(music)
    return {
        "schema_version": 2,
        "internal_credit_rub": _amount(InternalCreditService.rub_per_credit()),
        "admin_free": admin_free,
        "max_generation_quantity": MAX_REQUEST_QUANTITY,
        "families": build_model_families(models),
        "models": models,
    }


@router.post("/quote")
async def quote_generation(
    payload: CreateGenerationRequest,
    user: OptionalCurrentUserDep,
    session: SessionDep,
) -> dict[str, Any]:
    quantity = payload.quantity
    if MusicGenerationService.is_music_model(payload.model_id):
        try:
            _clean, retail_cost = MusicGenerationService.prepare(payload.parameters, payload.prompt)
        except MusicGenerationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        retail_total = _total(retail_cost, quantity)
        billing = None
        if user is not None:
            billing = await BillingAccessService.decision(
                session,
                user_id=user.id,
                retail_cost=retail_total,
            )
        effective_cost = billing.effective_cost if billing else retail_total
        admin_free = bool(billing and billing.admin_free)
        return {
            "model_id": MUSIC_MODEL_ID,
            "price_mode": "flat",
            "quantity": quantity,
            "unit_price_credits": _amount(retail_cost),
            "unit_price_rox": _amount(retail_cost),
            "unit_price_rub": _amount(InternalCreditService.rubles_for(retail_cost)),
            "billing_seconds": None,
            "cost_credits": _amount(retail_total),
            "cost_rox": _amount(retail_total),
            "cost_rub": _amount(InternalCreditService.rubles_for(retail_total)),
            "effective_cost_credits": _amount(effective_cost),
            "effective_cost_rox": _amount(effective_cost),
            "effective_cost_rub": _amount(InternalCreditService.rubles_for(effective_cost)),
            "retail_cost_rox": _amount(retail_total),
            "admin_free": admin_free,
            "internal_credit_rub": _amount(InternalCreditService.rub_per_credit()),
        }

    try:
        spec, _clean, retail_cost, seconds, retail_unit_price = await GenerationService.prepare_request(
            session,
            model_id=payload.model_id,
            prompt=payload.prompt,
            input_url=payload.input_url,
            parameters=payload.parameters,
            billing_seconds=payload.billing_seconds,
        )
    except (UnknownModelError, InvalidModelParametersError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    retail_total = _total(retail_cost, quantity)
    billing = None
    if user is not None:
        billing = await BillingAccessService.decision(
            session,
            user_id=user.id,
            retail_cost=retail_total,
        )
    effective_cost = billing.effective_cost if billing else retail_total
    admin_free = bool(billing and billing.admin_free)
    return {
        "model_id": spec.id,
        "price_mode": spec.price_mode,
        "quantity": quantity,
        "unit_price_credits": _amount(retail_unit_price),
        "unit_price_rox": _amount(retail_unit_price),
        "unit_price_rub": _amount(InternalCreditService.rubles_for(retail_unit_price)),
        "billing_seconds": seconds,
        "cost_credits": _amount(retail_total),
        "cost_rox": _amount(retail_total),
        "cost_rub": _amount(InternalCreditService.rubles_for(retail_total)),
        "effective_cost_credits": _amount(effective_cost),
        "effective_cost_rox": _amount(effective_cost),
        "effective_cost_rub": _amount(InternalCreditService.rubles_for(effective_cost)),
        "retail_cost_rox": _amount(retail_total),
        "admin_free": admin_free,
        "internal_credit_rub": _amount(InternalCreditService.rub_per_credit()),
    }


@router.get("")
async def list_generations(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=50),
    before: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
) -> dict[str, object]:
    statement = (
        select(Generation)
        .outerjoin(
            GenerationHistoryState,
            and_(
                GenerationHistoryState.generation_id == Generation.id,
                GenerationHistoryState.user_id == user.id,
            ),
        )
        .where(
            Generation.user_id == user.id,
            or_(
                GenerationHistoryState.generation_id.is_(None),
                GenerationHistoryState.hidden_at.is_(None),
            ),
        )
    )
    if status_filter:
        statement = statement.where(Generation.status == status_filter)

    if before is not None:
        anchor = await session.get(Generation, before)
        if anchor is None or anchor.user_id != user.id:
            raise HTTPException(status_code=404, detail="History cursor not found")
        statement = statement.where(
            or_(
                Generation.created_at < anchor.created_at,
                and_(Generation.created_at == anchor.created_at, Generation.id < anchor.id),
            )
        )

    rows = list(
        (
            await session.scalars(
                statement.order_by(Generation.created_at.desc(), Generation.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    media = await _owned_media_views(session, user_id=user.id, generations=page)
    return {
        "items": [
            _generation_view(row, owned_media=media.get(row.id, []))
            for row in page
        ],
        "has_more": has_more,
        "next_before": str(page[-1].id) if has_more and page else None,
    }


@router.get("/{generation_id}")
async def get_generation(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    generation = await _owned_generation(generation_id, user, session)
    history_state = await session.get(GenerationHistoryState, generation.id)
    hidden = bool(history_state and history_state.user_id == user.id and history_state.hidden_at)
    media = await _owned_media_views(session, user_id=user.id, generations=[generation])
    return _generation_view(generation, hidden=hidden, owned_media=media.get(generation.id, []))


@router.get("/{generation_id}/recreate")
async def recreate_generation_payload(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    generation = await _owned_generation(generation_id, user, session)
    return _recreate_payload_for_generation(generation)


@router.delete("/{generation_id}/history")
async def hide_generation_from_history(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, bool]:
    generation = await _owned_generation(generation_id, user, session)
    state = await session.get(GenerationHistoryState, generation.id)
    if state is None:
        state = GenerationHistoryState(generation_id=generation.id, user_id=user.id)
        session.add(state)
    elif state.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    state.hidden_at = datetime.now(timezone.utc)
    await session.commit()
    return {"hidden": True}


@router.post("/{generation_id}/history/restore")
async def restore_generation_to_history(
    generation_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, bool]:
    generation = await _owned_generation(generation_id, user, session)
    state = await session.get(GenerationHistoryState, generation.id)
    if state is not None:
        if state.user_id != user.id:
            raise HTTPException(status_code=404, detail="Generation not found")
        state.hidden_at = None
        await session.commit()
    return {"hidden": False}


@router.post("", status_code=202)
async def create_generation(
    payload: CreateGenerationRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, str | bool | None | int | list[str]]:
    try:
        if MusicGenerationService.is_music_model(payload.model_id):
            generations = await MusicGenerationService.create_many(
                session,
                redis,
                user_id=user.id,
                prompt=payload.prompt,
                parameters=payload.parameters,
                quantity=payload.quantity,
            )
        else:
            generations = await GenerationService.create_many(
                session,
                redis,
                user_id=user.id,
                model_id=payload.model_id,
                prompt=payload.prompt,
                input_url=payload.input_url,
                parameters=payload.parameters,
                billing_seconds=payload.billing_seconds,
                quantity=payload.quantity,
            )
    except (UnknownModelError, InvalidModelParametersError, MusicGenerationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=409, detail="Insufficient credits") from exc

    first = generations[0]
    total_cost = sum((Decimal(item.cost_rox) for item in generations), Decimal("0.00"))
    admin_free = bool((first.parameters or {}).get("_admin_free"))
    return {
        "id": str(first.id),
        "ids": [str(item.id) for item in generations],
        "quantity": len(generations),
        "status": first.status,
        "cost_credits": _amount(total_cost),
        "cost_rox": _amount(total_cost),
        "cost_rub": _amount(InternalCreditService.rubles_for(total_cost)),
        "admin_free": admin_free,
        "result_url": first.result_url,
    }
