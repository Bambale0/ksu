"""Execute frozen media-prompt routes without replaying an uncertain paid request elsewhere."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.observability import request_id_var
from app.db.prompt_tool_models import PromptToolTask
from app.providers.neironych_errors import NeironychProviderError, error_disposition
from app.providers.neironych_qwen_prompt_tools import (
    NeironychQwenPromptToolsClient,
    qwen_idempotency_key,
)
from app.providers.nexus_prompt_tools import NEXUS_VISION_MODEL, NexusPromptToolsClient
from app.services.abuse_protection import (
    AbuseProtectionService,
    ProviderCircuitOpen,
    ResourcePolicyError,
)
from app.services.prompt_tool_routing import prompt_tool_route_options
from app.services.prompt_tools import ClaimedPromptTool, PromptToolOutboxService

logger = logging.getLogger(__name__)
_QWEN_SNAPSHOT = "_qwen_submission"
_NEXUS_STARTED = "_prompt_tool_nexus_started"


class _StaleClaim(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _target(task: PromptToolTask) -> tuple[list[dict[str, str]], int, dict[str, str]]:
    data = task.input_payload or {}
    route = data.get("_prompt_tool_route")
    index = data.get("_prompt_tool_route_index")
    revision = data.get("_prompt_tool_route_revision")
    if (
        route not in prompt_tool_route_options().get(task.tool, [])
        or type(index) is not int or not 0 <= index < len(route)
        or type(revision) is not int or revision < 1
    ):
        raise ValueError("Invalid saved media-prompt route")
    target = route[index]
    if (task.provider, task.model) != (target["provider"], target["model"]):
        raise ValueError("Saved media-prompt identity changed")
    return route, index, target


async def _locked_task(session: AsyncSession, claimed: ClaimedPromptTool) -> PromptToolTask:
    locked = await PromptToolOutboxService._lock_current_claim(session, claimed)
    if locked is None:
        await session.rollback()
        raise _StaleClaim
    task, row = locked
    until = row.lease_until
    if until is not None and until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    if task.status not in {"queued", "processing"} or until is None or until <= _now():
        await session.rollback()
        raise _StaleClaim
    _target(task)
    return task


def _credential_digest() -> str:
    # Private identity guard, never logged: a rotated partner key must not turn
    # recovery of an existing paid request into admission under another account.
    return hashlib.sha256(settings.neironych_api_key.strip().encode()).hexdigest()


def _snapshot(task: PromptToolTask, body: str) -> dict[str, Any]:
    origin = settings.neironych_api_base_url.rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
        or parsed.path or parsed.query or parsed.fragment
    ):
        raise ValueError("Invalid Neironych origin")
    return {
        "version": 1,
        "base_url": origin,
        "endpoint": "/v1/chat/completions",
        "model": task.model,
        "idempotency_key": qwen_idempotency_key(task.id, task.tool),
        "client_request_id": str(task.id),
        "credential_sha256": _credential_digest(),
        "body_json": body,
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "created_at": _now().isoformat(),
    }


def _saved_body(task: PromptToolTask, snapshot: object) -> str:
    if not isinstance(snapshot, dict):
        raise ValueError("Invalid saved Qwen request")
    expected = {
        "version": 1,
        "base_url": settings.neironych_api_base_url.rstrip("/"),
        "endpoint": "/v1/chat/completions",
        "model": task.model,
        "idempotency_key": qwen_idempotency_key(task.id, task.tool),
        "client_request_id": str(task.id),
        "credential_sha256": _credential_digest(),
    }
    if any(snapshot.get(key) != value for key, value in expected.items()):
        raise ValueError("Saved Qwen request identity changed")
    body = snapshot.get("body_json")
    if not isinstance(body, str) or hashlib.sha256(body.encode()).hexdigest() != snapshot.get("sha256"):
        raise ValueError("Saved Qwen request integrity failed")
    payload = json.loads(body)
    if not isinstance(payload, dict) or payload.get("model") != task.model:
        raise ValueError("Saved Qwen request model changed")
    return body


async def _advance(
    session: AsyncSession, claimed: ClaimedPromptTool, *, provider: str, reason: str,
) -> bool:
    task = await _locked_task(session, claimed)
    route, index, target = _target(task)
    if target["provider"] != provider:
        await session.rollback()
        raise _StaleClaim
    if index + 1 >= len(route):
        await session.rollback()
        return False
    data = dict(task.input_payload or {})
    history = list(data.get("_prompt_tool_provider_history") or [])
    history.append({
        "provider": task.provider, "model": task.model,
        "reason_code": reason, "at": _now().isoformat(),
    })
    data.update({"_prompt_tool_route_index": index + 1, "_prompt_tool_provider_history": history})
    task.input_payload = data
    task.provider, task.model = route[index + 1]["provider"], route[index + 1]["model"]
    await session.commit()
    logger.warning(
        "prompt_tool_media_fallback task_id=%s provider=%s next_provider=%s reason_code=%s",
        claimed.task_id, provider, route[index + 1]["provider"], reason,
    )
    return True


async def _retry_or_fail(
    session: AsyncSession, claimed: ClaimedPromptTool, *, code: str,
    recovery: bool = False, retry_after: int | None = None,
) -> str:
    task = await _locked_task(session, claimed)
    recover_until = False
    snapshot = (task.input_payload or {}).get(_QWEN_SNAPSHOT)
    if recovery and isinstance(snapshot, dict):
        try:
            created = datetime.fromisoformat(snapshot["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            recover_until = 0 <= (_now() - created).total_seconds() < max(
                1, settings.generation_submission_unknown_timeout_seconds,
            )
        except (KeyError, TypeError, ValueError):
            recover_until = False
    await session.commit()
    if recover_until or (not recovery and claimed.attempts < settings.generation_submission_max_attempts):
        await PromptToolOutboxService.release(
            session, claimed, f"Анализ временно недоступен ({code}).",
            retry_after_seconds=max(30 if recovery else 0, retry_after or 0),
        )
        return "recovery_pending" if recovery else "retry_pending"
    return await _fail(session, claimed, code)


async def _fail(session: AsyncSession, claimed: ClaimedPromptTool, code: str) -> str:
    logger.warning("prompt_tool_media_failed task_id=%s reason_code=%s", claimed.task_id, code)
    await PromptToolOutboxService.fail_and_refund(
        session, claimed, error="Не удалось завершить анализ. Попробуйте ещё раз позже.",
    )
    return "failed"


async def _qwen_call(session: AsyncSession, claimed: ClaimedPromptTool):
    task = await _locked_task(session, claimed)
    if task.provider != "neironych":
        await session.rollback()
        raise _StaleClaim
    data, model, tool = dict(task.input_payload or {}), task.model, task.tool
    existing = data.get(_QWEN_SNAPSHOT)
    body = _saved_body(task, existing) if existing is not None else None
    await session.commit()
    client = NeironychQwenPromptToolsClient(settings.neironych_api_key, settings.neironych_api_base_url)
    try:
        if body is None:
            if tool == "image_analysis":
                prepared = await client.prepare_image_request(
                    image_url=str(data.get("image_url") or ""),
                    instruction=str(data.get("instruction") or ""), model=model,
                )
            else:
                raw_duration = data.get("duration_seconds")
                prepared = await client.prepare_video_request(
                    video_url=str(data.get("video_url") or ""),
                    instruction=str(data.get("instruction") or ""),
                    duration_seconds=int(raw_duration) if raw_duration else None, model=model,
                )
            # Extraction may outlive the original claim. Recheck before freezing
            # a request and never perform HTTP while holding a database row lock.
            task = await _locked_task(session, claimed)
            if (task.provider, task.model) != ("neironych", model):
                raise _StaleClaim
            current = dict(task.input_payload or {})
            if current.get(_QWEN_SNAPSHOT) is None:
                current[_QWEN_SNAPSHOT] = _snapshot(task, prepared)
                task.input_payload = current
            body = _saved_body(task, current[_QWEN_SNAPSHOT])
            await session.commit()
        # A second execution of this same claim can only replay the exact body
        # and task key at Neironych; it cannot create another upstream operation.
        return await client.submit(request_body=body, task_id=claimed.task_id, tool=tool, model=model)
    finally:
        await client.aclose()


async def _nexus_call(session: AsyncSession, claimed: ClaimedPromptTool):
    task = await _locked_task(session, claimed)
    if task.provider != "nexus":
        await session.rollback()
        raise _StaleClaim
    if task.model != NEXUS_VISION_MODEL:
        raise ValueError("Saved Nexus model is not supported by this adapter")
    data, tool = dict(task.input_payload or {}), task.tool
    if data.get(_NEXUS_STARTED):
        await session.rollback()
        raise ValueError("Nexus outcome cannot be safely resubmitted")
    client = NexusPromptToolsClient(
        settings.nexus_api_key, settings.nexus_api_base_url, media_max_attempts=1,
    )
    try:
        data[_NEXUS_STARTED] = {"at": _now().isoformat(), "attempt": claimed.attempts}
        task.input_payload = data
        await session.commit()
        if tool == "image_analysis":
            return await client.analyze_image(
                image_url=str(data.get("image_url") or ""),
                instruction=str(data.get("instruction") or ""),
            )
        raw_duration = data.get("duration_seconds")
        return await client.build_video_prompt(
            video_url=str(data.get("video_url") or ""),
            instruction=str(data.get("instruction") or ""),
            duration_seconds=int(raw_duration) if raw_duration else None,
        )
    finally:
        await client.aclose()


async def _run(
    session: AsyncSession, redis: Redis, claimed: ClaimedPromptTool, context: dict[str, Any],
) -> str:
    # Validated routes contain each of the two supported providers at most once.
    for _ in range(2):
        task = await _locked_task(session, claimed)
        _route, _index, target = _target(task)
        provider, model = target["provider"], target["model"]
        data = dict(task.input_payload or {})
        recovering = provider == "neironych" and _QWEN_SNAPSHOT in data
        nexus_started = provider == "nexus" and bool(data.get(_NEXUS_STARTED))
        context.update(provider=provider, model=model, tool=task.tool,
                       revision=data["_prompt_tool_route_revision"])
        await session.commit()
        protection = f"{provider}-prompt-tools"
        try:
            if nexus_started:
                return await _fail(session, claimed, "nexus_submission_outcome_unknown")
            await AbuseProtectionService.provider_submission_gate(redis, protection)
            if provider == "neironych":
                result = await _qwen_call(session, claimed)
            else:
                if not settings.nexus_api_key.strip():
                    if await _advance(session, claimed, provider=provider, reason="api_key_required"):
                        continue
                    return await _fail(session, claimed, "api_key_required")
                result = await _nexus_call(session, claimed)
            if result.model != model:
                return await _fail(session, claimed, "provider_model_mismatch")
            task = await _locked_task(session, claimed)
            if (task.provider, task.model) != (provider, model):
                raise _StaleClaim
            # Keep the current-claim lock through completion so a discarded
            # response cannot be logged as success by a superseded worker.
            await PromptToolOutboxService.complete(
                session, claimed, result=result.payload, model=model,
                provider_credits=result.credits_consumed,
            )
            await AbuseProtectionService.record_provider_success(redis, protection)
            return "succeeded"
        except _StaleClaim:
            raise
        except ProviderCircuitOpen:
            await session.rollback()
            if not recovering and await _advance(session, claimed, provider=provider, reason="circuit_open"):
                continue
            return await _retry_or_fail(session, claimed, code="circuit_open", recovery=recovering)
        except ResourcePolicyError as exc:
            # A quota or unavailable protection store is not a provider failure
            # and does not authorize going around the protection via a reserve.
            await session.rollback()
            context["error_code"] = exc.code
            return await _retry_or_fail(
                session, claimed, code=exc.code, recovery=recovering,
                retry_after=exc.retry_after,
            )
        except NeironychProviderError as exc:
            await session.rollback()
            await AbuseProtectionService.record_provider_failure(redis, protection)
            disposition = error_disposition(exc)
            code = exc.error_code or "provider_error"
            context["error_code"] = code
            # An auth failure during recovery does not prove that the original
            # request was never accepted. A fenced rejection receipt does.
            if disposition == "fallback" and (not recovering or exc.submission_rejected):
                if await _advance(session, claimed, provider=provider, reason=code):
                    continue
            if disposition == "uncertain" and code != "prompt_response_invalid":
                return await _retry_or_fail(
                    session, claimed, code=code, recovery=True, retry_after=exc.retry_after,
                )
            return await _fail(session, claimed, code)
        except Exception as exc:
            await session.rollback()
            await AbuseProtectionService.record_provider_failure(redis, protection)
            context["error_code"] = type(exc).__name__
            # Nexus has no verified supplier replay protocol. Its durable start
            # marker prevents a crash/timeout from becoming another paid POST.
            return await _fail(session, claimed, "media_analysis_failed")
    return await _fail(session, claimed, "provider_route_exhausted")


async def process_media_prompt(
    session: AsyncSession, redis: Redis, claimed: ClaimedPromptTool,
) -> None:
    started = time.monotonic()
    token = request_id_var.set(f"prompt-tool:{claimed.task_id}")
    context: dict[str, Any] = {"provider": "unknown", "model": "unknown", "tool": "unknown", "revision": 0}
    outcome = "failed"
    try:
        async with asyncio.timeout(settings.prompt_tool_media_timeout_seconds):
            outcome = await _run(session, redis, claimed, context)
    except _StaleClaim:
        await session.rollback()
        outcome = "stale_claim"
    except TimeoutError:
        await session.rollback()
        try:
            task = await _locked_task(session, claimed)
            can_recover = task.provider == "neironych" and _QWEN_SNAPSHOT in (task.input_payload or {})
            await session.commit()
            outcome = await _retry_or_fail(session, claimed, code="execution_timeout", recovery=True) if can_recover else await _fail(session, claimed, "execution_timeout")
        except _StaleClaim:
            outcome = "stale_claim"
    except Exception as exc:
        await session.rollback()
        context["error_code"] = type(exc).__name__
        outcome = await _fail(session, claimed, "invalid_media_prompt_state")
    finally:
        logger.info(
            "prompt_tool_media task_id=%s tool=%s provider=%s model=%s revision=%s attempt=%s "
            "outcome=%s error_code=%s elapsed_ms=%.1f",
            claimed.task_id, context["tool"], context["provider"], context["model"],
            context["revision"], claimed.attempts, outcome, context.get("error_code", "none"),
            (time.monotonic() - started) * 1000,
        )
        request_id_var.reset(token)
