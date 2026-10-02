from __future__ import annotations

import io
import json
import logging
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation
from app.providers.neironych_errors import error_disposition, request_identifier
from app.providers.neironych_image import NeironychImageClient, prepare_image_payload
from app.providers.neironych_submission import SNAPSHOT_KEY, freeze_submission, saved_body
from app.providers.neironych_video import (
    NeironychProviderError,
    NeironychVideoClient,
    is_failure_status,
    is_success_status,
)
from app.services.feed_static import FeedStaticStorage
from app.services.generation_provider import GenerationProviderService
from app.services.generation_provider_routing import idempotency_key, switch_to_fallback
from app.services.generation_reliability import GenerationOutboxService
from app.services.media_assets import MediaAssetService
from app.services.neironych_video_contracts import (
    NeironychVideoContractError,
    normalize_neironych_video_input,
)
from app.services.reference_static import ReferenceStaticStorage
from app.services.neironych_reference_validation import validate_reference_payload, ReferenceValidationError

logger = logging.getLogger(__name__)

_SEEDANCE_MODELS = frozenset({"seedance-2.0", "seedance-2.5"})
_HANDLED_MODELS = _SEEDANCE_MODELS | {"nano-banana-pro"}
_POLICY_MARKERS = (
    "copyright",
    "moderation",
    "safety",
    "nsfw",
    "policy",
    "forbidden content",
    "content violation",
)


class NeironychGenerationProviderService:
    @staticmethod
    def _model_id(generation: Generation) -> str:
        return str((generation.parameters or {}).get("_model_id") or "").strip()

    @classmethod
    def handles(cls, generation: Generation) -> bool:
        return cls._model_id(generation) in _HANDLED_MODELS

    @staticmethod
    def _public_reference_url(raw: str) -> str:
        value = str(raw or "").strip()
        if not value:
            raise ValueError("Reference URL must not be empty")
        parsed = urlsplit(value)
        if parsed.scheme == "https" and parsed.netloc:
            return value
        if not (
            ReferenceStaticStorage.is_local_url(value)
            or FeedStaticStorage.is_local_url(value)
        ):
            raise ValueError("Reference must be an HTTPS or product-owned media URL")
        base = urlsplit(settings.public_base_url.strip())
        if base.scheme != "https" or not base.netloc:
            raise ValueError("PUBLIC_BASE_URL must be HTTPS for Neironych references")
        return urlunsplit((base.scheme, base.netloc, parsed.path or value.split("?", 1)[0], "", ""))

    @staticmethod
    def _policy_error(error: str) -> bool:
        lowered = str(error or "").lower()
        return any(marker in lowered for marker in _POLICY_MARKERS)

    @classmethod
    async def _fallback_or_fail(
        cls,
        session: AsyncSession,
        generation: Generation,
        *,
        reason: str,
        terminal_failure: bool = False,
    ) -> Generation:
        fallback = await switch_to_fallback(
            session, generation.id, reason=reason, expected_provider="neironych",
            terminal_failure=terminal_failure,
        )
        if fallback is not None:
            logger.warning(
                "neironych_fallback generation=%s model=%s next_provider=%s reason=%s",
                generation.id,
                cls._model_id(generation),
                fallback.provider,
                str(reason)[:300],
            )
            return fallback
        # Another worker may have bound/completed/switched the attempt while the
        # provider request was in flight. Never refund that newer state.
        if generation.provider != "neironych" or generation.status in {"succeeded", "failed"}:
            return generation
        if generation.external_id and not terminal_failure:
            # A concurrent worker already bound an accepted provider task (for
            # example after replaying the same idempotency key). A late
            # fallback-eligible error must not discard authoritative upstream
            # work; the bound task keeps polling to a terminal outcome.
            return generation
        if (generation.parameters or {}).get("_submission_uncertain") and not terminal_failure:
            return generation
        await GenerationProviderService.fail_and_refund(session, generation.id, reason)
        refreshed = await session.get(Generation, generation.id)
        if refreshed is None:
            raise LookupError("Generation disappeared after Neironych failure")
        return refreshed

    @classmethod
    async def _mark_video_retry(
        cls,
        session: AsyncSession,
        generation: Generation,
        *,
        error: str,
    ) -> Generation:
        locked = await session.scalar(
            select(Generation).where(Generation.id == generation.id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked is None:
            raise LookupError("Generation disappeared after Neironych submission")
        if locked.status in {"succeeded", "failed"} or locked.provider != "neironych" or locked.external_id:
            return locked
        locked.provider = "neironych"
        locked.status = "retry"
        locked.error = str(error)[:4000]
        locked.external_id = None
        params = dict(locked.parameters or {})
        params["_submission_uncertain"] = True
        params.setdefault("_submission_uncertain_at", datetime.now(timezone.utc).isoformat())
        locked.parameters = params
        await session.commit()
        return locked

    @classmethod
    async def _mark_image_uncertain(
        cls,
        session: AsyncSession,
        generation: Generation,
        *,
        error: str,
    ) -> Generation:
        locked = await session.scalar(
            select(Generation).where(Generation.id == generation.id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked is None:
            raise LookupError("Generation disappeared after Neironych image submission")
        if locked.provider != "neironych" or locked.status in {"succeeded", "failed"}:
            return locked
        now = datetime.now(timezone.utc)
        locked.provider = "neironych"
        locked.status = "submitting"
        locked.error = f"Neironych image outcome uncertain: {error}"[:4000]
        params = dict(locked.parameters or {})
        params["_submission_uncertain"] = True
        params.setdefault("_submission_uncertain_at", now.isoformat())
        locked.parameters = params
        await session.commit()
        return locked

    @classmethod
    async def _complete_local_file(
        cls,
        session: AsyncSession,
        generation_id: uuid.UUID,
        *,
        path: Path,
        content_type: str,
        source_url: str,
    ) -> Generation:
        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if generation is None:
            raise LookupError("Generation disappeared before Neironych completion")
        if generation.status in {"succeeded", "failed"} or generation.provider != "neironych":
            return generation

        asset = await MediaAssetService.persist_ready_local_file(
            session,
            generation,
            path=path,
            content_type=content_type,
            source_url=source_url,
        )
        view = MediaAssetService.public_view(asset)
        relative = str(view["url"])
        result_url = (
            relative
            if relative.startswith("https://")
            else settings.public_base_url.rstrip("/") + "/" + relative.lstrip("/")
        )
        generation.status = "succeeded"
        generation.error = None
        generation.result_url = result_url
        generation.parameters = {
            **dict(generation.parameters or {}),
            "_result_urls": [result_url],
        }
        generation.updated_at = datetime.now(timezone.utc)
        await GenerationProviderService._award_prompt_repeat_bonus(session, generation)
        await session.commit()
        await GenerationOutboxService.mark_generation_terminal(
            session,
            generation.id,
            failed=False,
        )
        return generation

    @classmethod
    async def _record_response(
        cls, session: AsyncSession, generation: Generation, *,
        request_id: str | None = None, error: NeironychProviderError | None = None,
    ) -> Generation:
        # The same session may hold an old identity-map value after provider I/O.
        expected_key = idempotency_key(generation)
        locked = await session.scalar(
            select(Generation).where(Generation.id == generation.id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked is None:
            raise LookupError("Generation disappeared after provider response")
        if locked.provider != "neironych" or locked.status in {"succeeded", "failed"} or idempotency_key(locked) != expected_key:
            return locked
        params = dict(locked.parameters or {})
        metadata = {
            "provider": "neironych", "idempotency_key": expected_key,
            "request_id": request_identifier(error.request_id if error else request_id),
            "http_status": error.status_code if error else 200,
            "error_code": error.error_code if error else None,
            "retry_after": error.retry_after if error else None,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        params["_provider_response"] = metadata
        locked.parameters = params
        await session.flush()
        logger.info("neironych_response generation=%s provider_request_id=%s status=%s code=%s",
                    locked.id, metadata["request_id"], metadata["http_status"], metadata["error_code"])
        return locked

    @classmethod
    async def _handle_submission_error(
        cls, session: AsyncSession, generation: Generation, exc: NeironychProviderError,
        *, video: bool,
    ) -> Generation:
        locked = await cls._record_response(session, generation, error=exc)
        if locked.provider != "neironych" or locked.status in {"succeeded", "failed"} or locked.external_id:
            return locked
        disposition = error_disposition(exc)
        message = str(exc) if exc.local_validation else (
            f"Neironych API HTTP {exc.status_code}: {exc.error_code or 'unclassified_provider_error'}"
        )
        if disposition == "fallback":
            return await cls._fallback_or_fail(session, locked, reason=message)
        if disposition == "reject":
            await GenerationProviderService.fail_and_refund(session, locked.id, message)
            return locked
        if video:
            return await cls._mark_video_retry(session, locked, error=message)
        return await cls._mark_image_uncertain(session, locked, error=message)

    @classmethod
    async def _freeze_new_submission(cls, session: AsyncSession, generation: Generation) -> None:
        params = dict(generation.parameters or {})
        model = cls._model_id(generation)
        key = idempotency_key(generation)
        snapshot = params.get(SNAPSHOT_KEY)
        if snapshot is not None:
            saved_body(snapshot, model=model, key=key, base_url=settings.neironych_api_base_url)
            return
        if params.get("_submission_uncertain"):
            # Pre-upgrade unknown POST has no immutable original wire body. Do
            # not guess a new body/key. Bound tasks remain pollable as before.
            raise ValueError("Original Neironych request body unavailable; reconciliation required")
        raw = GenerationProviderService._input_for(generation)
        endpoint = "/v1/videos/generations"
        if model in _SEEDANCE_MODELS:
            payload = normalize_neironych_video_input(model, raw)
            await validate_reference_payload(model, payload)
        else:
            refs_raw = raw.get("image_input") or raw.get("image_urls") or []
            refs_raw = refs_raw if isinstance(refs_raw, (list, tuple)) else [refs_raw]
            refs = [cls._public_reference_url(str(item.get("url") if isinstance(item, dict) else item))
                    for item in refs_raw]
            endpoint, payload = prepare_image_payload(
                prompt=str(raw.get("prompt") or generation.prompt or ""),
                aspect_ratio=str(raw.get("aspect_ratio") or "1:1"),
                resolution=str(raw.get("resolution") or raw.get("image_size") or "2K"),
                image_urls=refs, idempotency_key=key,
            )
        snapshot = freeze_submission(model=model, payload=payload, key=key,
            base_url=settings.neironych_api_base_url, endpoint=endpoint)
        snapshot["output_format"] = str(raw.get("output_format") or "jpg")
        params[SNAPSHOT_KEY] = snapshot
        generation.parameters = params
        # Caller commits this together with submitting before any paid POST.

    @classmethod
    async def submit(cls, session: AsyncSession, generation_id: uuid.UUID) -> Generation:
        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if generation is None:
            raise LookupError("Generation not found")
        if generation.status not in {"queued", "retry"} or generation.external_id:
            return generation
        if str(generation.provider or "") != "neironych" or not cls.handles(generation):
            raise ValueError("Generation is not routed to Neironych")

        model_id = cls._model_id(generation)
        try:
            await cls._freeze_new_submission(session, generation)
        except NeironychVideoContractError as exc:
            # Only known Kie-compatible settings may cross providers. Malformed
            # input or media is a validation failure, never a policy bypass.
            if "generate_audio=false" in str(exc) or "aspect_ratio=adaptive" in str(exc):
                return await cls._fallback_or_fail(session, generation, reason=f"Neironych contract: {exc}")
            await GenerationProviderService.fail_and_refund(session, generation.id, str(exc))
            return generation
        except NeironychProviderError as exc:
            raw = GenerationProviderService._input_for(generation)
            if model_id == "nano-banana-pro" and raw.get("aspect_ratio") == "auto":
                # Legacy drafts/explicit Nexus auto requests remain valid on
                # Nexus. Never silently turn auto into a square image.
                return await cls._fallback_or_fail(session, generation, reason="Neironych does not support aspect_ratio=auto")
            return await cls._handle_submission_error(session, generation, exc, video=model_id in _SEEDANCE_MODELS)
        except (ValueError, ReferenceValidationError) as exc:
            if (generation.parameters or {}).get("_submission_uncertain"):
                return await cls._mark_video_retry(session, generation, error=str(exc))
            await GenerationProviderService.fail_and_refund(session, generation.id, str(exc))
            return generation
        generation.status = "submitting"
        generation.error = None
        await session.commit()

        if model_id in _SEEDANCE_MODELS:
            return await cls._submit_video(session, generation_id)
        return await cls._submit_image(session, generation_id)

    @classmethod
    async def _submit_video(cls, session: AsyncSession, generation_id: uuid.UUID) -> Generation:
        generation = await session.get(Generation, generation_id)
        if generation is None:
            raise LookupError("Generation not found")
        model_id = cls._model_id(generation)
        snapshot = (generation.parameters or {})[SNAPSHOT_KEY]
        body = saved_body(snapshot, model=model_id, key=idempotency_key(generation),
                          base_url=settings.neironych_api_base_url)
        client = None
        try:
            client = NeironychVideoClient(settings.neironych_api_key, settings.neironych_api_base_url)
            request_id = await client.create_video(
                model=model_id, payload=json.loads(body), request_body=body,
                idempotency_key=idempotency_key(generation),
            )
        except NeironychProviderError as exc:
            return await cls._handle_submission_error(session, generation, exc, video=True)
        except httpx.RequestError as exc:
            return await cls._mark_video_retry(session, generation, error=type(exc).__name__)
        finally:
            if client is not None:
                await client.aclose()

        locked = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked is None:
            raise LookupError("Generation disappeared after Neironych submission")
        if locked.status in {"succeeded", "failed"} or locked.provider != "neironych":
            return locked
        if locked.external_id and locked.external_id != request_id:
            raise RuntimeError("Neironych request identity changed")
        locked.external_id = request_id
        locked.provider = "neironych"
        locked.status = "generating"
        locked.error = None
        params = dict(locked.parameters or {})
        params["_provider_response"] = {
            "provider": "neironych", "request_id": request_identifier(request_id),
            "http_status": 202, "error_code": None,
            "idempotency_key": idempotency_key(locked),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        params.pop("_submission_uncertain", None)
        params.pop("_submission_uncertain_at", None)
        locked.parameters = params
        GenerationProviderService._mark_provider_task_bound(
            locked,
            now=datetime.now(timezone.utc),
        )
        await session.commit()
        return locked

    @classmethod
    async def _submit_image(cls, session: AsyncSession, generation_id: uuid.UUID) -> Generation:
        generation = await session.get(Generation, generation_id)
        if generation is None:
            raise LookupError("Generation not found")
        snapshot = (generation.parameters or {})[SNAPSHOT_KEY]
        body = saved_body(snapshot, model="nano-banana-pro", key=idempotency_key(generation),
                          base_url=settings.neironych_api_base_url)
        payload = json.loads(body)
        refs = [item["image_url"] for item in payload.get("images", [])]
        client = None
        try:
            client = NeironychImageClient(settings.neironych_api_key, settings.neironych_api_base_url)
            result = await client.create_nano_banana_pro(
                prompt=payload["prompt"], aspect_ratio=payload["aspect_ratio"],
                resolution=payload["resolution"], image_urls=refs,
                idempotency_key=idempotency_key(generation), request_body=body,
            )
        except NeironychProviderError as exc:
            return await cls._handle_submission_error(session, generation, exc, video=False)
        except httpx.RequestError as exc:
            return await cls._mark_image_uncertain(session, generation, error=type(exc).__name__)
        finally:
            if client is not None:
                await client.aclose()

        generation = await cls._record_response(session, generation, request_id=result.request_id)
        if generation.status in {"succeeded", "failed"} or generation.provider != "neironych":
            return generation
        output_format = str(snapshot.get("output_format") or "jpg").strip().lower()
        if output_format == "jpeg":
            output_format = "jpg"
        suffix = ".png" if output_format == "png" else ".jpg"
        content_type = "image/png" if output_format == "png" else "image/jpeg"
        handle = tempfile.NamedTemporaryFile(
            prefix="ksu-neironych-image-",
            suffix=suffix,
            delete=False,
        )
        path = Path(handle.name)
        try:
            if output_format == "png":
                with Image.open(io.BytesIO(result.content)) as image:
                    image.save(handle, format="PNG")
            else:
                handle.write(result.content)
            handle.close()
            return await cls._complete_local_file(
                session,
                generation.id,
                path=path,
                content_type=content_type,
                source_url=f"neironych://image/{generation.id}{suffix}",
            )
        finally:
            try:
                handle.close()
            except Exception:
                pass
            path.unlink(missing_ok=True)

    @classmethod
    async def sync_video(
        cls,
        session: AsyncSession,
        *,
        request_id: str,
        generation_id: uuid.UUID,
    ) -> Generation | None:
        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if generation is None or generation.status in {"succeeded", "failed"}:
            return generation
        if generation.provider != "neironych" or generation.external_id != request_id:
            return generation

        # The outbox and recovery scan can reach the same upstream task.
        # Atomically reserve its next GET so both honor provider poll cadence.
        now = datetime.now(timezone.utc)
        params = dict(generation.parameters or {})
        next_poll = params.get("_neironych_next_poll_at")
        if next_poll:
            try:
                if datetime.fromisoformat(next_poll) > now:
                    return generation
            except (TypeError, ValueError):
                pass
        params["_neironych_next_poll_at"] = (now + timedelta(seconds=settings.neironych_poll_seconds)).isoformat()
        generation.parameters = params
        await session.commit()

        client = NeironychVideoClient(settings.neironych_api_key, settings.neironych_api_base_url)
        try:
            try:
                status, provider_error, _ = await client.get_video(request_id)
            except NeironychProviderError as exc:
                generation = await cls._record_response(session, generation, error=exc)
                if generation.provider == "neironych" and generation.status not in {"succeeded", "failed"}:
                    delay = max(settings.neironych_poll_seconds, exc.retry_after or 0)
                    generation.parameters = {**(generation.parameters or {}),
                        "_neironych_next_poll_at": (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()}
                    await session.commit()
                return generation
            if is_success_status(status):
                handle = tempfile.NamedTemporaryFile(
                    prefix="ksu-neironych-video-",
                    suffix=".mp4",
                    delete=False,
                )
                path = Path(handle.name)
                handle.close()
                try:
                    content_type = await client.download_content_to(
                        request_id,
                        path,
                        max_bytes=settings.media_ingest_max_bytes,
                    )
                    return await cls._complete_local_file(
                        session,
                        generation.id,
                        path=path,
                        content_type=content_type or "video/mp4",
                        source_url=f"neironych://video/{request_id}",
                    )
                finally:
                    path.unlink(missing_ok=True)
            if is_failure_status(status):
                generation = await session.scalar(
                    select(Generation).where(Generation.id == generation_id).with_for_update()
                    .execution_options(populate_existing=True)
                )
                if generation is None or generation.status in {"succeeded", "failed"}:
                    return generation
                if generation.provider != "neironych" or generation.external_id != request_id:
                    return generation
                reason = provider_error or f"Neironych generation failed ({status})"
                technical = status == "expired" or any(
                    marker in reason.lower()
                    for marker in ("timeout", "timed out", "unavailable", "internal server error")
                )
                if technical and not cls._policy_error(reason):
                    return await cls._fallback_or_fail(
                        session, generation, reason=reason, terminal_failure=True,
                    )
                await GenerationProviderService.fail_and_refund(session, generation.id, reason)
                return await session.get(Generation, generation.id)

            locked = await session.scalar(
                select(Generation).where(Generation.id == generation_id).with_for_update()
            )
            if locked is None or locked.status in {"succeeded", "failed"}:
                return locked
            if locked.provider != "neironych" or locked.external_id != request_id:
                return locked
            locked.status = "generating"
            locked.error = None
            locked.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return locked
        finally:
            await client.aclose()
