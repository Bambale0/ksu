from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.db.batch_models import BatchGenerationJob
from app.services.abuse_protection import ResourcePolicyError
from app.services.batch_generation_core import BatchGenerationError, BatchIdempotencyConflict, amount
from app.services.batch_recovery import BatchRecoveryService
from app.services.batch_repository import BatchRepository
from app.services.generation_batches import GenerationBatchService
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/batch-generations", tags=["batch-generations"])


class BatchWrite(BaseModel):
    model_id: str = Field(min_length=1, max_length=128)
    prompt: str = Field(default="", max_length=8000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    billing_seconds: int | None = Field(default=None, ge=1, le=600)
    input_urls: list[str] = Field(default_factory=list, max_length=20)
    reference_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


def _domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, BatchIdempotencyConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, InsufficientBalanceError):
        return HTTPException(status_code=409, detail="Insufficient credits")
    if isinstance(exc, ResourcePolicyError):
        return HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": str(exc.retry_after)})
    if isinstance(exc, (BatchGenerationError, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


async def _view(session: SessionDep, job: BatchGenerationJob, *, replayed: bool | None = None) -> dict[str, Any]:
    batch_status, succeeded, failed, active = await BatchRepository.refresh(session, job)
    rows = await BatchRepository.rows(session, job.id)
    metadata = job.parameters or {}
    admin_free = bool(metadata.get("_admin_free"))
    retail_total = Decimal(str(metadata.get("_retail_total_cost_rox") or job.initial_cost_rox))
    payload: dict[str, Any] = {
        "id": str(job.id), "status": batch_status, "model_id": job.model_id, "prompt": job.prompt,
        "parameters": {key: value for key, value in metadata.items() if not str(key).startswith("_")},
        "billing_seconds": job.billing_seconds, "input_count": job.input_count,
        "succeeded_count": succeeded, "failed_count": failed, "active_count": active,
        "progress_percent": int(((succeeded + failed) / max(1, job.input_count)) * 100),
        "initial_cost_credits": amount(job.initial_cost_rox), "total_charged_credits": amount(job.total_charged_rox),
        "retail_initial_cost_credits": amount(retail_total), "admin_free": admin_free,
        "items": [{
            "id": str(item.id), "ordinal": item.ordinal, "input_url": item.input_url, "retry_count": item.retry_count,
            "generation": {"id": str(generation.id), "status": generation.status, "result_url": generation.result_url, "error": generation.error, "cost_credits": amount(generation.cost_rox)},
        } for item, generation in rows],
        "created_at": job.created_at.isoformat(), "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
    if replayed is not None:
        payload["replayed"] = replayed
    return payload


@router.post("/quote")
async def quote_batch(payload: BatchWrite, user: CurrentUserDep, session: SessionDep) -> dict[str, Any]:
    try:
        return await GenerationBatchService.quote(session, user_id=user.id, **payload.model_dump())
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_batch(payload: BatchWrite, user: CurrentUserDep, session: SessionDep, redis: RedisDep, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
    try:
        job, replayed = await GenerationBatchService.create(session, redis, user_id=user.id, idempotency_key=idempotency_key, **payload.model_dump())
        return await _view(session, job, replayed=replayed)
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc


@router.get("")
async def list_batches(user: CurrentUserDep, session: SessionDep, limit: int = Query(default=20, ge=1, le=50)) -> dict[str, Any]:
    jobs = list((await session.scalars(select(BatchGenerationJob).where(BatchGenerationJob.user_id == user.id).order_by(BatchGenerationJob.created_at.desc()).limit(limit))).all())
    return {"items": [await _view(session, job) for job in jobs]}


@router.get("/{batch_id}")
async def get_batch(batch_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> dict[str, Any]:
    try:
        job = await BatchRepository.load(session, user_id=user.id, batch_id=batch_id)
        return await _view(session, job)
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.get("/{batch_id}/retry-quote")
async def retry_quote(batch_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    try:
        return await BatchRecoveryService.quote(session, user_id=user.id, batch_id=batch_id)
    except Exception as exc:
        raise _domain_error(exc) from exc


@router.post("/{batch_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_batch(batch_id: uuid.UUID, user: CurrentUserDep, session: SessionDep, redis: RedisDep, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
    try:
        job, replayed, retried_count = await BatchRecoveryService.execute(session, redis, user_id=user.id, batch_id=batch_id, idempotency_key=idempotency_key)
        payload = await _view(session, job, replayed=replayed)
        payload["retried_count"] = retried_count
        return payload
    except Exception as exc:
        await session.rollback()
        raise _domain_error(exc) from exc
