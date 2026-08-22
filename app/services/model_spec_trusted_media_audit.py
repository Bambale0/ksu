from __future__ import annotations

import math
import uuid
from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select

_INSTALLED = False

_DURATION_BILLED_REFERENCE_MODELS = {
    "kling-avatar-standard",
    "kling-avatar-pro",
    "kling-motion-2.6",
    "kling-motion-3.0",
}
_GROK_TASK_MODELS = {"grok-video-i2v", "grok-video-upscale", "grok-video-extend"}


def _seconds_from_ms(value: Any) -> int | None:
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        return None
    if milliseconds <= 0:
        return None
    return max(1, math.ceil(milliseconds / 1000))


def _first_url(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list) and value:
        return str(value[0] or "").strip()
    return ""


def _is_auto_duration(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return float(value) == 0
    except (TypeError, ValueError):
        return False


def _requires_trusted_billing(model_id: str, parameters: dict[str, Any]) -> bool:
    if model_id in _DURATION_BILLED_REFERENCE_MODELS:
        return True
    if model_id == "wan-2.7-video-edit":
        return _is_auto_duration(parameters.get("duration", 0))
    if model_id == "gemini-omni-video":
        return bool(parameters.get("video_list"))
    return model_id == "grok-video-upscale" and bool(parameters.get("task_id"))


async def _reference_for_url(
    session: Any,
    *,
    url: str,
    user_id: uuid.UUID | None = None,
):
    from app.db.reference_models import UserReference

    statement = select(UserReference).where(
        UserReference.status == "ready",
        UserReference.source_url == url,
    )
    if user_id is not None:
        statement = statement.where(UserReference.user_id == user_id)
    statement = statement.order_by(UserReference.created_at.desc()).limit(1)
    return await session.scalar(statement)


async def _require_reference_seconds(
    session: Any,
    *,
    url: str,
    label: str,
    user_id: uuid.UUID | None = None,
) -> int:
    from app.services.model_catalog import InvalidModelParametersError

    if not url:
        raise InvalidModelParametersError(f"{label} reference is required")
    row = await _reference_for_url(session, url=url, user_id=user_id)
    if row is None:
        raise InvalidModelParametersError(
            f"{label} duration must be verified: upload this media through ROXY"
        )
    seconds = _seconds_from_ms(row.duration_ms)
    if row.probe_status != "ready" or seconds is None:
        raise InvalidModelParametersError(
            f"{label} duration is not verified: re-upload this media through ROXY"
        )
    return seconds


async def _task_source(
    session: Any,
    *,
    task_id: str,
    user_id: uuid.UUID | None = None,
):
    from app.db.models import Generation

    statement = select(Generation).where(Generation.external_id == task_id)
    if user_id is not None:
        statement = statement.where(Generation.user_id == user_id)
    return await session.scalar(statement.limit(1))


def _validate_grok_source(source: Any, *, operation: str) -> None:
    from app.services.model_catalog import InvalidModelParametersError

    if source is None:
        raise InvalidModelParametersError(f"{operation} requires one of your completed Grok tasks")
    params = source.parameters or {}
    if source.status != "success" or str(params.get("_model_family") or "") != "grok":
        raise InvalidModelParametersError(f"{operation} requires one of your completed Grok tasks")


async def _grok_source_seconds(session: Any, *, task_id: str) -> int:
    from app.services.model_catalog import InvalidModelParametersError

    source = await _task_source(session, task_id=task_id)
    _validate_grok_source(source, operation="Grok Upscale")
    raw = (source.parameters or {}).get("_billing_seconds")
    try:
        seconds = int(raw)
    except (TypeError, ValueError) as exc:
        raise InvalidModelParametersError(
            "Grok source duration is unavailable; recreate the source video before upscaling"
        ) from exc
    if seconds <= 0:
        raise InvalidModelParametersError("Grok source duration must be positive")
    return seconds


async def _gemini_video_seconds(session: Any, video_list: Any) -> int:
    from app.services.model_catalog import InvalidModelParametersError

    if not isinstance(video_list, list) or len(video_list) != 1 or not isinstance(video_list[0], dict):
        raise InvalidModelParametersError("Gemini Omni accepts exactly one video item when video input is used")
    item = video_list[0]
    url = str(item.get("url") or "").strip()
    source_seconds = await _require_reference_seconds(
        session,
        url=url,
        label="Gemini source video",
    )

    try:
        start = float(item.get("start", 0) or 0)
        ends_raw = item.get("ends")
        ends = float(ends_raw) if ends_raw not in (None, "") else float(source_seconds)
    except (TypeError, ValueError) as exc:
        raise InvalidModelParametersError("Gemini video start/ends must be numeric seconds") from exc
    if start < 0 or ends <= start:
        raise InvalidModelParametersError("Gemini video ends must be greater than start")
    if ends > source_seconds + 0.05:
        raise InvalidModelParametersError("Gemini video segment exceeds the verified source duration")
    selected = max(1, math.ceil(ends - start))
    if selected > 10:
        raise InvalidModelParametersError("Gemini Omni video input is limited to a 10-second selected segment")
    return selected


async def _reference_total_seconds(
    session: Any,
    *,
    urls: Any,
    label: str,
) -> int:
    from app.services.model_catalog import InvalidModelParametersError

    if urls in (None, "", []):
        return 0
    if not isinstance(urls, list):
        raise InvalidModelParametersError(f"{label} references must be an array")
    total = 0
    for raw in urls:
        total += await _require_reference_seconds(
            session,
            url=str(raw or "").strip(),
            label=label,
        )
    return total


async def resolve_trusted_billing_seconds(
    session: Any,
    *,
    model_id: str,
    parameters: dict[str, Any],
    client_billing_seconds: int | None,
) -> int | None:
    """Return billing duration derived from provider-driving media where required."""

    if model_id in {"kling-avatar-standard", "kling-avatar-pro"}:
        return await _require_reference_seconds(
            session,
            url=str(parameters.get("audio_url") or "").strip(),
            label="Kling Avatar audio",
        )

    if model_id in {"kling-motion-2.6", "kling-motion-3.0"}:
        return await _require_reference_seconds(
            session,
            url=_first_url(parameters.get("video_urls")),
            label="Kling Motion video",
        )

    if model_id == "wan-2.7-video-edit" and _is_auto_duration(parameters.get("duration", 0)):
        return await _require_reference_seconds(
            session,
            url=str(parameters.get("video_url") or "").strip(),
            label="Wan source video",
        )

    if model_id == "gemini-omni-video" and parameters.get("video_list"):
        return await _gemini_video_seconds(session, parameters.get("video_list"))

    if model_id == "grok-video-upscale":
        task_id = str(parameters.get("task_id") or "").strip()
        if not task_id:
            return client_billing_seconds
        return await _grok_source_seconds(session, task_id=task_id)

    return client_billing_seconds


async def validate_reference_duration_contracts(
    session: Any,
    *,
    model_id: str,
    parameters: dict[str, Any],
) -> None:
    from app.services.model_catalog import InvalidModelParametersError

    if model_id in {"seedance-2.0", "seedance-2.0-fast", "seedance-2.0-mini"}:
        video_total = await _reference_total_seconds(
            session,
            urls=parameters.get("reference_video_urls"),
            label="Seedance reference video",
        )
        audio_total = await _reference_total_seconds(
            session,
            urls=parameters.get("reference_audio_urls"),
            label="Seedance reference audio",
        )
        if video_total > 15:
            raise InvalidModelParametersError("Seedance 2.0 reference videos may total at most 15 seconds")
        if audio_total > 15:
            raise InvalidModelParametersError("Seedance 2.0 reference audio may total at most 15 seconds")

    if model_id == "seedance-2.5":
        video_total = await _reference_total_seconds(
            session,
            urls=parameters.get("reference_video_urls"),
            label="Seedance 2.5 reference video",
        )
        audio_total = await _reference_total_seconds(
            session,
            urls=parameters.get("reference_audio_urls"),
            label="Seedance 2.5 reference audio",
        )
        if video_total > 30:
            raise InvalidModelParametersError("Seedance 2.5 reference videos may total at most 30 seconds")
        if audio_total > 30:
            raise InvalidModelParametersError("Seedance 2.5 reference audio may total at most 30 seconds")


async def validate_owned_trusted_sources(
    session: Any,
    *,
    user_id: uuid.UUID,
    model_id: str,
    parameters: dict[str, Any],
) -> None:
    """Create-time ownership boundary for media/task-derived generation inputs."""

    if model_id in {"kling-avatar-standard", "kling-avatar-pro"}:
        await _require_reference_seconds(
            session,
            user_id=user_id,
            url=str(parameters.get("audio_url") or "").strip(),
            label="Kling Avatar audio",
        )
    elif model_id in {"kling-motion-2.6", "kling-motion-3.0"}:
        await _require_reference_seconds(
            session,
            user_id=user_id,
            url=_first_url(parameters.get("video_urls")),
            label="Kling Motion video",
        )
    elif model_id == "wan-2.7-video-edit" and _is_auto_duration(parameters.get("duration", 0)):
        await _require_reference_seconds(
            session,
            user_id=user_id,
            url=str(parameters.get("video_url") or "").strip(),
            label="Wan source video",
        )
    elif model_id == "gemini-omni-video" and parameters.get("video_list"):
        video = parameters["video_list"][0] if isinstance(parameters["video_list"], list) and parameters["video_list"] else {}
        if isinstance(video, dict):
            await _require_reference_seconds(
                session,
                user_id=user_id,
                url=str(video.get("url") or "").strip(),
                label="Gemini source video",
            )

    if model_id in _GROK_TASK_MODELS and parameters.get("task_id"):
        operation = {
            "grok-video-i2v": "Grok I2V",
            "grok-video-upscale": "Grok Upscale",
            "grok-video-extend": "Grok Extend",
        }[model_id]
        source = await _task_source(
            session,
            task_id=str(parameters.get("task_id") or "").strip(),
            user_id=user_id,
        )
        _validate_grok_source(source, operation=operation)


def install_model_spec_trusted_media_audit() -> None:
    """Make media-derived duration and Grok task ownership server-authoritative."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import model_ui_contract as ui_contract
    from app.services.generations import GenerationService
    from app.services.model_routing import resolve_model_request
    from app.services.reference_size_contract import validate_reference_sizes
    from app.services.references import ReferenceService

    previous_prepare = GenerationService.prepare_request

    @classmethod
    async def trusted_prepare(
        cls: type[GenerationService],
        session: Any,
        *,
        model_id: str,
        prompt: str,
        input_url: str | None = None,
        parameters: dict[str, Any] | None = None,
        billing_seconds: int | None = None,
    ):
        source_parameters = dict(parameters or {})
        if prompt and not source_parameters.get("prompt"):
            source_parameters["prompt"] = prompt
        routed = resolve_model_request(model_id, source_parameters, input_url=input_url)

        # Only media-derived billing needs database metadata before ModelCatalog can
        # compute a price. Every other request goes through the normal structural
        # model validation first, so malformed payloads fail before optional media
        # lookups and keep quote/preflight deterministic.
        trusted_seconds = billing_seconds
        if _requires_trusted_billing(routed.model_id, routed.parameters):
            trusted_seconds = await resolve_trusted_billing_seconds(
                session,
                model_id=routed.model_id,
                parameters=routed.parameters,
                client_billing_seconds=billing_seconds,
            )

        spec, clean, cost, seconds, unit_price = await previous_prepare(
            session,
            model_id=model_id,
            prompt=prompt,
            input_url=input_url,
            parameters=parameters,
            billing_seconds=trusted_seconds,
        )

        await validate_reference_sizes(
            session,
            spec=spec,
            parameters=clean,
        )
        await validate_reference_duration_contracts(
            session,
            model_id=spec.id,
            parameters=clean,
        )

        # Gemini ignores `duration` when video_list is supplied. Keep the valid
        # provider duration field for the payload, but price the verified source
        # segment instead of that ignored field.
        if spec.id == "gemini-omni-video" and clean.get("video_list"):
            if trusted_seconds is None:
                raise RuntimeError("Gemini trusted duration resolution unexpectedly failed")
            seconds = trusted_seconds
            cost = (unit_price * Decimal(seconds)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return spec, clean, cost, seconds, unit_price

    GenerationService.prepare_request = trusted_prepare

    previous_create = GenerationService.create

    @classmethod
    async def trusted_create(
        cls: type[GenerationService],
        session: Any,
        redis: Any,
        *,
        user_id: uuid.UUID,
        model_id: str,
        prompt: str = "",
        input_url: str | None = None,
        parameters: dict[str, Any] | None = None,
        billing_seconds: int | None = None,
        source_feed_gen_id: uuid.UUID | None = None,
        parent_generation_id: uuid.UUID | None = None,
        action_type: str | None = None,
    ):
        source_parameters = dict(parameters or {})
        if prompt and not source_parameters.get("prompt"):
            source_parameters["prompt"] = prompt
        routed = resolve_model_request(model_id, source_parameters, input_url=input_url)
        await validate_owned_trusted_sources(
            session,
            user_id=user_id,
            model_id=routed.model_id,
            parameters=routed.parameters,
        )
        return await previous_create(
            session,
            redis,
            user_id=user_id,
            model_id=model_id,
            prompt=prompt,
            input_url=input_url,
            parameters=parameters,
            billing_seconds=billing_seconds,
            source_feed_gen_id=source_feed_gen_id,
            parent_generation_id=parent_generation_id,
            action_type=action_type,
        )

    GenerationService.create = trusted_create

    previous_schema = ui_contract.build_public_model_ui_schema

    def trusted_schema(model: dict[str, Any]) -> dict[str, Any]:
        schema = deepcopy(previous_schema(model))
        model_id = str(model.get("id") or "")
        if model_id in _DURATION_BILLED_REFERENCE_MODELS or model_id == "wan-2.7-video-edit":
            schema.pop("billing_seconds", None)
            schema["billing_source"] = "reference_metadata"
        if model_id == "gemini-omni-video":
            schema["video_billing_source"] = "verified_video_segment"
        return schema

    ui_contract.build_public_model_ui_schema = trusted_schema

    previous_reference_view = ReferenceService.public_view

    def trusted_reference_view(row: Any) -> dict[str, Any]:
        view = previous_reference_view(row)
        view.update(
            {
                "size_bytes": row.size_bytes,
                "duration_ms": row.duration_ms,
                "duration_seconds": _seconds_from_ms(row.duration_ms),
                "width": row.width,
                "height": row.height,
                "container": row.container,
                "video_codec": row.video_codec,
                "audio_codec": row.audio_codec,
                "probe_status": row.probe_status,
            }
        )
        return view

    ReferenceService.public_view = staticmethod(trusted_reference_view)
