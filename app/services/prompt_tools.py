from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from urllib.parse import urlsplit

from redis.asyncio import Redis
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.admin_models import TariffVersion
from app.db.prompt_tool_models import PromptToolOutbox, PromptToolTask
from app.providers.kie_prompt_tools import KiePromptToolsClient, PromptToolProviderError
from app.services.abuse_protection import AbuseProtectionService
from app.services.billing_policy import BillingPolicyService
from app.services.wallet import WalletService

logger = logging.getLogger(__name__)

PromptToolName = Literal["image_analysis", "prompt_builder"]

_TOOL_MODEL = {
    "image_analysis": "gemini-2.5-pro",
    "prompt_builder": "gpt-5-5",
}
_TOOL_TITLE = {
    "image_analysis": "Промпт по фото",
    "prompt_builder": "Улучшить промпт",
}
_TASK_NAMESPACE = uuid.UUID("b9346c9a-31c2-4de6-b2dd-0c76c359dd7f")


class PromptToolUnavailable(RuntimeError):
    pass


class PromptToolIdempotencyConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ClaimedPromptTool:
    outbox_id: uuid.UUID
    task_id: uuid.UUID
    attempts: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _retry_delay(attempt: int) -> int:
    return min(180, 2 ** max(1, min(attempt, 7)))


class PromptToolPricingService:
    @staticmethod
    async def prices(session: AsyncSession) -> dict[str, Decimal]:
        tariff = await session.scalar(
            select(TariffVersion)
            .where(TariffVersion.status == "published")
            .order_by(TariffVersion.version.desc())
            .limit(1)
        )
        if tariff is None:
            return {}
        raw = (tariff.payload or {}).get("prompt_costs") or {}
        if not isinstance(raw, dict):
            return {}
        result: dict[str, Decimal] = {}
        for tool in _TOOL_MODEL:
            value = raw.get(tool)
            if isinstance(value, dict):
                value = value.get("credits")
            try:
                amount = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if amount > 0:
                result[tool] = amount.quantize(Decimal("0.01"))
        return result

    @classmethod
    async def price(cls, session: AsyncSession, tool: PromptToolName) -> Decimal:
        prices = await cls.prices(session)
        amount = prices.get(tool)
        if amount is None:
            raise PromptToolUnavailable(
                f"{tool} is disabled until prompt_costs.{tool} is published in pricing"
            )
        return amount

    @classmethod
    async def catalog(cls, session: AsyncSession) -> dict[str, Any]:
        prices = await cls.prices(session)
        return {
            "items": [
                {
                    "id": tool,
                    "title": _TOOL_TITLE[tool],
                    "enabled": tool in prices,
                    "cost_credits": format(prices[tool], ".2f") if tool in prices else None,
                    "cost_rub": (
                        format(prices[tool] * settings.internal_credit_rub, ".2f")
                        if tool in prices
                        else None
                    ),
                }
                for tool in _TOOL_MODEL
            ]
        }


class PromptToolService:
    @staticmethod
    def _normalize_input(tool: PromptToolName, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or "").strip()
        image_url_raw = str(payload.get("image_url") or "").strip()
        instruction = str(payload.get("instruction") or "").strip()
        if len(text) > 8000:
            raise ValueError("Text must be at most 8000 characters")
        if len(instruction) > 1000:
            raise ValueError("Instruction must be at most 1000 characters")
        image_url = PromptToolService._safe_image_url(image_url_raw) if image_url_raw else None
        if tool == "image_analysis":
            if image_url is None:
                raise ValueError("image_url is required")
            return {"image_url": image_url, "instruction": instruction}
        if not text and image_url is None:
            raise ValueError("text or image_url is required")
        return {"text": text, "image_url": image_url}

    @staticmethod
    def _safe_image_url(value: str) -> str:
        if len(value) > 4000:
            raise ValueError("image_url is too long")
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("image_url must be an HTTPS URL")
        host = (parsed.hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
            raise ValueError("Local image URLs are not allowed")
        return value

    @staticmethod
    def _request_hash(tool: PromptToolName, payload: dict[str, Any]) -> str:
        raw = json.dumps(
            {"tool": tool, "payload": payload},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @classmethod
    async def create_task(
        cls,
        session: AsyncSession,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        tool: PromptToolName,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> tuple[PromptToolTask, bool]:
        clean_key = idempotency_key.strip()
        if len(clean_key) < 8 or len(clean_key) > 128:
            raise ValueError("Idempotency-Key must contain 8..128 characters")
        clean = cls._normalize_input(tool, payload)
        task_id = uuid.uuid5(_TASK_NAMESPACE, f"{user_id}:{clean_key}")
        request_hash = cls._request_hash(tool, clean)

        existing = await session.get(PromptToolTask, task_id)
        if existing is not None:
            stored_hash = str((existing.input_payload or {}).get("_request_hash") or "")
            if existing.tool != tool or stored_hash != request_hash:
                raise PromptToolIdempotencyConflict("Idempotency-Key was already used for another request")
            return existing, True

        await AbuseProtectionService.consume(
            redis,
            key=f"abuse:prompt-tools:user:{user_id}",
            limit=max(1, settings.generation_rate_limit_per_minute),
            window_seconds=60,
            message="Prompt tools rate limit exceeded",
        )
        price = await PromptToolPricingService.price(session, tool)
        admin_free = await BillingPolicyService.user_has_free_bot_access(session, user_id)
        charge = Decimal("0.00") if admin_free else price
        task = PromptToolTask(
            id=task_id,
            user_id=user_id,
            tool=tool,
            status="queued",
            provider="kie",
            model=_TOOL_MODEL[tool],
            input_payload={
                **clean,
                "_request_hash": request_hash,
                **(
                    {"_admin_free_generation": True, "_quoted_cost_credits": str(price)}
                    if admin_free
                    else {}
                ),
            },
            result_payload={},
            cost_credits=charge,
        )
        session.add(task)
        session.add(PromptToolOutbox(task_id=task.id))
        await session.flush()
        if charge > 0:
            await WalletService.debit(
                session,
                user_id=user_id,
                amount=charge,
                kind="prompt_tool",
                reference_type="prompt_tool_task",
                reference_id=str(task.id),
                idempotency_key=f"prompt-tool:{task.id}:charge",
            )
        await session.commit()
        try:
            await redis.rpush("wake:prompt-tools", str(task.id))
        except Exception:
            logger.warning("Prompt tool wake-up failed for %s; outbox will recover it", task.id)
        return task, False

    @staticmethod
    async def get_owned(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> PromptToolTask:
        task = await session.get(PromptToolTask, task_id)
        if task is None or task.user_id != user_id:
            raise LookupError("Prompt tool task not found")
        return task

    @staticmethod
    def public_view(task: PromptToolTask, *, replayed: bool = False) -> dict[str, Any]:
        return {
            "id": str(task.id),
            "tool": task.tool,
            "status": task.status,
            "model": task.model,
            "cost_credits": format(Decimal(task.cost_credits), ".2f"),
            "cost_rub": format(Decimal(task.cost_credits) * settings.internal_credit_rub, ".2f"),
            "result": task.result_payload if task.status == "succeeded" else None,
            "error": task.error if task.status == "failed" else None,
            "has_image": bool((task.input_payload or {}).get("image_url")),
            "created_at": task.created_at.isoformat(),
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "idempotency_replayed": replayed,
        }


class PromptToolOutboxService:
    @staticmethod
    async def claim(session: AsyncSession) -> ClaimedPromptTool | None:
        now = _utcnow()
        row = await session.scalar(
            select(PromptToolOutbox)
            .where(
                PromptToolOutbox.available_at <= now,
                or_(
                    PromptToolOutbox.status == "pending",
                    and_(
                        PromptToolOutbox.status == "processing",
                        PromptToolOutbox.lease_until.is_not(None),
                        PromptToolOutbox.lease_until < now,
                    ),
                ),
            )
            .order_by(PromptToolOutbox.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return None
        row.status = "processing"
        row.attempts += 1
        row.lease_until = now + timedelta(seconds=settings.generation_outbox_lease_seconds)
        row.last_error = None
        task = await session.get(PromptToolTask, row.task_id)
        if task is not None and task.status in {"queued", "processing"}:
            task.status = "processing"
        await session.commit()
        return ClaimedPromptTool(row.id, row.task_id, row.attempts)

    @staticmethod
    async def release(session: AsyncSession, claimed: ClaimedPromptTool, error: str) -> None:
        row = await session.get(PromptToolOutbox, claimed.outbox_id)
        if row is None:
            return
        row.status = "pending"
        row.lease_until = None
        row.available_at = _utcnow() + timedelta(seconds=_retry_delay(claimed.attempts))
        row.last_error = error[:4000]
        task = await session.get(PromptToolTask, claimed.task_id)
        if task is not None:
            task.status = "queued"
        await session.commit()

    @staticmethod
    async def complete(
        session: AsyncSession,
        claimed: ClaimedPromptTool,
        *,
        result: dict[str, Any],
        model: str,
        provider_credits: Decimal | None,
    ) -> None:
        now = _utcnow()
        task = await session.get(PromptToolTask, claimed.task_id)
        row = await session.get(PromptToolOutbox, claimed.outbox_id)
        if task is None or row is None:
            return
        task.status = "succeeded"
        task.model = model
        task.result_payload = result
        task.provider_credits = provider_credits
        task.error = None
        task.completed_at = now
        row.status = "completed"
        row.lease_until = None
        row.completed_at = now
        row.last_error = None
        await session.commit()

    @staticmethod
    async def fail_and_refund(
        session: AsyncSession,
        claimed: ClaimedPromptTool,
        *,
        error: str,
    ) -> None:
        now = _utcnow()
        task = await session.get(PromptToolTask, claimed.task_id)
        row = await session.get(PromptToolOutbox, claimed.outbox_id)
        if task is None or row is None:
            return
        task.status = "failed"
        task.error = error[:4000]
        task.completed_at = now
        row.status = "failed"
        row.lease_until = None
        row.completed_at = now
        row.last_error = error[:4000]
        if task.cost_credits > 0:
            await WalletService.credit(
                session,
                user_id=task.user_id,
                amount=Decimal(task.cost_credits),
                kind="prompt_tool_refund",
                reference_type="prompt_tool_task",
                reference_id=str(task.id),
                idempotency_key=f"prompt-tool:{task.id}:refund",
            )
        await session.commit()


class PromptToolProcessor:
    @staticmethod
    async def process(
        session: AsyncSession,
        redis: Redis,
        claimed: ClaimedPromptTool,
    ) -> None:
        task = await session.get(PromptToolTask, claimed.task_id)
        if task is None:
            return
        try:
            await AbuseProtectionService.provider_submission_gate(redis, "kie-prompt-tools")
            client = KiePromptToolsClient(settings.kie_api_key, settings.kie_base_url)
            try:
                data = task.input_payload or {}
                if task.tool == "image_analysis":
                    result = await client.analyze_image(
                        image_url=str(data.get("image_url") or ""),
                        instruction=str(data.get("instruction") or ""),
                    )
                elif task.tool == "prompt_builder":
                    result = await client.build_prompt(
                        text=str(data.get("text") or ""),
                        image_url=str(data.get("image_url") or "") or None,
                    )
                else:
                    raise ValueError(f"Unknown prompt tool: {task.tool}")
            finally:
                await client.aclose()
            await PromptToolOutboxService.complete(
                session,
                claimed,
                result=result.payload,
                model=result.model,
                provider_credits=result.credits_consumed,
            )
            await AbuseProtectionService.record_provider_success(redis, "kie-prompt-tools")
        except Exception as exc:
            await session.rollback()
            await AbuseProtectionService.record_provider_failure(redis, "kie-prompt-tools")
            if claimed.attempts < settings.generation_submission_max_attempts:
                await PromptToolOutboxService.release(session, claimed, str(exc))
                return
            await PromptToolOutboxService.fail_and_refund(session, claimed, error=str(exc))
            if not isinstance(exc, PromptToolProviderError):
                logger.exception("Prompt tool task %s failed", claimed.task_id)
