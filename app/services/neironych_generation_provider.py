from __future__ import annotations

import io
import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation
from app.providers.neironych_image import NeironychImageClient
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
    ) -> Generation:
        fallback = await switch_to_fallback(session, generation.id, reason=reason)
        if fallback is not None:
            logger.warning(
                "neironych_fallback generation=%s model=%s next_provider=%s reason=%s",
                generation.id,
                cls._model_id(generation),
                fallback.provider,
                str(reason)[:300],
            )
            return fallback
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
        )
        if locked is None:
            raise LookupError("Generation disappeared after Neironych submission")
        if locked.status in {"succeeded", "failed"}:
            return locked
        locked.provider = "neironych"
        locked.status = "retry"
        locked.error = str(error)[:4000]
        locked.external_id = None
        params = dict(locked.parameters or {})
        params.pop("_submission_uncertain", None)
        params.pop("_submission_uncertain_at", None)
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
        )
        if locked is None:
            raise LookupError("Generation disappeared after Neironych image submission")
        if locked.status in {"succeeded", "failed"}:
            return locked
        now = datetime.now(timezone.utc)
        locked.provider = "neironych"
        locked.status = "submitting"
        locked.error = f"Neironych image outcome uncertain: {error}"[:4000]
        params = dict(locked.parameters or {})
        params["_submission_uncertain"] = True
        params["_submission_uncertain_at"] = now.isoformat()
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
        )
        if generation is None:
            raise LookupError("Generation disappeared before Neironych completion")
        if generation.status == "succeeded":
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
    async def submit(cls, session: AsyncSession, generation_id: uuid.UUID) -> Generation:
        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if generation is None:
            raise LookupError("Generation not found")
        if generation.status not in {"queued", "retry"}:
            return generation
        if str(generation.provider or "") != "neironych" or not cls.handles(generation):
            raise ValueError("Generation is not routed to Neironych")

        model_id = cls._model_id(generation)
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
        raw = GenerationProviderService._input_for(generation)
        try:
            payload = normalize_neironych_video_input(model_id, raw)
        except NeironychVideoContractError as exc:
            return await cls._fallback_or_fail(session, generation, reason=f"Neironych contract: {exc}")

        client = NeironychVideoClient(settings.neironych_api_key, settings.neironych_api_base_url)
        try:
            try:
                request_id = await client.create_video(
                    model=model_id,
                    payload=payload,
                    idempotency_key=idempotency_key(generation),
                )
            except NeironychProviderError as exc:
                status = exc.status_code
                if (
                    status in {400, 401, 402, 403, 404, 405, 413, 415, 422, 429}
                    and not cls._policy_error(str(exc))
                ):
                    return await cls._fallback_or_fail(session, generation, reason=str(exc))
                if status is not None and 400 <= status < 500:
                    await GenerationProviderService.fail_and_refund(session, generation.id, str(exc))
                    refreshed = await session.get(Generation, generation.id)
                    if refreshed is None:
                        raise LookupError("Generation disappeared after Neironych rejection")
                    return refreshed
                return await cls._mark_video_retry(session, generation, error=str(exc))
            except httpx.RequestError as exc:
                return await cls._mark_video_retry(session, generation, error=str(exc))
        finally:
            await client.aclose()

        locked = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
        )
        if locked is None:
            raise LookupError("Generation disappeared after Neironych submission")
        if locked.external_id and locked.external_id != request_id:
            raise RuntimeError("Neironych request identity changed")
        locked.external_id = request_id
        locked.provider = "neironych"
        locked.status = "generating"
        locked.error = None
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
        raw = GenerationProviderService._input_for(generation)
        refs_raw = raw.get("image_input")
        if refs_raw in (None, ""):
            refs_raw = raw.get("image_urls")
        if refs_raw in (None, ""):
            refs: list[str] = []
        elif isinstance(refs_raw, (list, tuple)):
            refs = []
            for item in refs_raw:
                raw_url = item.get("url") if isinstance(item, dict) else item
                if str(raw_url or "").strip():
                    refs.append(cls._public_reference_url(str(raw_url)))
        else:
            raw_url = refs_raw.get("url") if isinstance(refs_raw, dict) else refs_raw
            refs = [cls._public_reference_url(str(raw_url))]

        client = NeironychImageClient(settings.neironych_api_key, settings.neironych_api_base_url)
        try:
            try:
                result = await client.create_nano_banana_pro(
                    prompt=str(raw.get("prompt") or generation.prompt or ""),
                    aspect_ratio=str(raw.get("aspect_ratio") or "1:1"),
                    resolution=str(raw.get("resolution") or raw.get("image_size") or "2K"),
                    image_urls=refs,
                    idempotency_key=idempotency_key(generation),
                )
            except NeironychProviderError as exc:
                status = exc.status_code
                if status == 409:
                    return await cls._mark_image_uncertain(session, generation, error=str(exc))
                if (
                    status in {400, 401, 402, 403, 404, 405, 413, 415, 422, 429}
                    and not cls._policy_error(str(exc))
                ):
                    return await cls._fallback_or_fail(session, generation, reason=str(exc))
                if status is not None and 400 <= status < 500:
                    await GenerationProviderService.fail_and_refund(session, generation.id, str(exc))
                    refreshed = await session.get(Generation, generation.id)
                    if refreshed is None:
                        raise LookupError("Generation disappeared after Neironych rejection")
                    return refreshed
                return await cls._mark_image_uncertain(session, generation, error=str(exc))
            except httpx.RequestError as exc:
                return await cls._mark_image_uncertain(session, generation, error=str(exc))
        finally:
            await client.aclose()

        output_format = str(raw.get("output_format") or "jpg").strip().lower()
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
        generation = await session.get(Generation, generation_id)
        if generation is None or generation.status in {"succeeded", "failed"}:
            return generation
        if generation.provider != "neironych" or generation.external_id != request_id:
            return generation

        client = NeironychVideoClient(settings.neironych_api_key, settings.neironych_api_base_url)
        try:
            status, provider_error, _ = await client.get_video(request_id)
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
                reason = provider_error or f"Neironych generation failed ({status})"
                if not cls._policy_error(reason):
                    return await cls._fallback_or_fail(session, generation, reason=reason)
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
