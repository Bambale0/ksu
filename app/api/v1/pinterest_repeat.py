from __future__ import annotations

import asyncio
import hashlib
import uuid
from decimal import Decimal
from functools import partial
from io import BytesIO
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.db.models import Generation
from app.services.abuse_protection import AbuseProtectionService
from app.services.billing_access import BillingAccessService
from app.services.credits import InternalCreditService
from app.services.generations import GenerationService
from app.services.model_catalog import InvalidModelParametersError, UnknownModelError
from app.services.pinterest_repeat import (
    PinterestRepeatError,
    PinterestRepeatGenerationRequest,
    PinterestRepeatService,
)
from app.services.reference_static import ReferenceStaticStorage, ReferenceStaticStorageError
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/pinterest-repeat", tags=["pinterest-repeat"])

PINTEREST_REPEAT_IDEMPOTENCY_NAMESPACE = uuid.UUID("f26d4567-a043-46ef-a229-eed93f2df31a")


class PinterestResolveRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class PinterestRepeatRequest(BaseModel):
    scene_reference_url: str = Field(min_length=8, max_length=4096)
    identity_reference_urls: list[str] = Field(min_length=1, max_length=5)
    height_cm: int = Field(ge=120, le=230)
    weight_kg: int = Field(ge=30, le=250)
    expression: str | None = Field(default=None, max_length=240)


def _amount(value: Decimal | str | int | float) -> str:
    return format(Decimal(str(value)), ".2f")


def _build(payload: PinterestRepeatRequest) -> PinterestRepeatGenerationRequest:
    try:
        return PinterestRepeatService.build_request(
            scene_reference_url=payload.scene_reference_url,
            identity_reference_urls=payload.identity_reference_urls,
            height_cm=payload.height_cm,
            weight_kg=payload.weight_kg,
            expression=payload.expression,
        )
    except PinterestRepeatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _run_view(generation: Generation, *, replayed: bool = False) -> dict[str, Any]:
    return {
        "id": str(generation.id),
        "status": generation.status,
        "mode": "pinterest_repeat",
        "cost_rox": _amount(generation.cost_rox),
        "admin_free": bool((generation.parameters or {}).get("_admin_free")),
        "idempotency_replayed": replayed,
    }


def _idempotent_generation_id(user_id: uuid.UUID, idempotency_key: str) -> uuid.UUID:
    clean_key = idempotency_key.strip()
    if len(clean_key) < 8 or len(clean_key) > 128:
        raise HTTPException(status_code=422, detail="Idempotency-Key должен содержать 8–128 символов")
    return uuid.uuid5(PINTEREST_REPEAT_IDEMPOTENCY_NAMESPACE, f"{user_id}:{clean_key}")


def _generation_matches_recipe(
    generation: Generation,
    recipe: PinterestRepeatGenerationRequest,
) -> bool:
    parameters = generation.parameters or {}
    stored_model_id = str(
        parameters.get("_requested_model_id")
        or parameters.get("_model_id")
        or ""
    )
    if stored_model_id != recipe.model_id or generation.prompt != recipe.prompt:
        return False
    return all(parameters.get(key) == value for key, value in recipe.parameters.items())


async def _replayed_generation(
    session: SessionDep,
    *,
    generation_id: uuid.UUID,
    user_id: uuid.UUID,
    recipe: PinterestRepeatGenerationRequest,
) -> Generation | None:
    generation = await session.get(Generation, generation_id)
    if generation is None:
        return None
    if generation.user_id != user_id or generation.action_type != "pinterest_repeat":
        raise HTTPException(status_code=409, detail="Idempotency-Key уже использован")
    if not _generation_matches_recipe(generation, recipe):
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key уже использован с другими параметрами",
        )
    return generation


@router.post("/resolve")
async def resolve_pinterest_reference(
    payload: PinterestResolveRequest,
    user: CurrentUserDep,
    redis: RedisDep,
) -> dict[str, str]:
    try:
        resolved = await PinterestRepeatService.resolve_reference(payload.url)
        downloaded = await PinterestRepeatService.download_reference_image(resolved.reference_url)
    except PinterestRepeatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    size_bytes = len(downloaded.content)
    await AbuseProtectionService.upload_rate_and_bytes(
        redis,
        user_id=user.id,
        size_bytes=size_bytes,
    )
    file_hash = hashlib.sha256(downloaded.content).hexdigest()
    stream = BytesIO(downloaded.content)
    try:
        local_url, _path, _stored_size = await asyncio.to_thread(
            partial(
                ReferenceStaticStorage.persist_stream,
                stream,
                user_id=user.id,
                kind="image",
                file_hash=file_hash,
                filename=downloaded.filename,
                content_type=downloaded.content_type,
                expected_size=size_bytes,
            )
        )
    except ReferenceStaticStorageError as exc:
        raise HTTPException(status_code=500, detail="Reference storage failed") from exc

    # Pinterest scene images deliberately do not enter UserReference. The stable
    # product-owned URL is enough for ProviderMediaTransport, while keeping the
    # user's reusable identity-reference library and its pruning quota untouched.
    return {
        "source_url": resolved.source_url,
        "reference_url": local_url,
    }


@router.post("/quote")
async def quote_pinterest_repeat(
    payload: PinterestRepeatRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, Any]:
    recipe = _build(payload)
    try:
        spec, _clean, retail_cost, seconds, retail_unit_price = await GenerationService.prepare_request(
            session,
            model_id=recipe.model_id,
            prompt=recipe.prompt,
            parameters=recipe.parameters,
        )
    except (UnknownModelError, InvalidModelParametersError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    billing = await BillingAccessService.decision(
        session,
        user_id=user.id,
        retail_cost=retail_cost,
    )
    effective = billing.effective_cost
    return {
        "mode": "pinterest_repeat",
        "model_id": spec.id,
        "unit_price_rox": _amount(retail_unit_price),
        "cost_rox": _amount(retail_cost),
        "effective_cost_rox": _amount(effective),
        "cost_rub": _amount(InternalCreditService.rubles_for(effective)),
        "retail_cost_rox": _amount(retail_cost),
        "billing_seconds": seconds,
        "admin_free": billing.admin_free,
    }


@router.post("/run", status_code=202)
async def run_pinterest_repeat(
    payload: PinterestRepeatRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, Any]:
    recipe = _build(payload)
    generation_id = _idempotent_generation_id(user.id, idempotency_key)
    existing = await _replayed_generation(
        session,
        generation_id=generation_id,
        user_id=user.id,
        recipe=recipe,
    )
    if existing is not None:
        return _run_view(existing, replayed=True)

    try:
        generation = await GenerationService.create(
            session,
            redis,
            user_id=user.id,
            model_id=recipe.model_id,
            prompt=recipe.prompt,
            parameters=recipe.parameters,
            action_type="pinterest_repeat",
            generation_id=generation_id,
        )
    except IntegrityError:
        # A concurrent retry can race the first request between the initial read
        # and INSERT. The deterministic primary key makes the loser fail before
        # wallet debit; after rollback it replays only if the request is identical.
        await session.rollback()
        replayed = await _replayed_generation(
            session,
            generation_id=generation_id,
            user_id=user.id,
            recipe=recipe,
        )
        if replayed is None:
            raise HTTPException(status_code=409, detail="Не удалось подтвердить повтор запроса")
        return _run_view(replayed, replayed=True)
    except (UnknownModelError, InvalidModelParametersError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=409, detail="Недостаточно ROX") from exc

    return _run_view(generation)
