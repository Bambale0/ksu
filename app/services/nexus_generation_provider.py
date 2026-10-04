from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation
from app.providers.kie import KieTask
from app.providers.nexus import NexusClient, NexusProviderError
from app.services.feed_static import FeedStaticStorage
from app.services.generation_provider import GenerationProviderService
from app.services.generation_provider_routing import switch_to_fallback
from app.services.reference_static import ReferenceStaticStorage


class NexusGenerationContractError(ValueError):
    pass


NEXUS_MODEL_MAP: dict[str, str] = {
    "nano-banana": "nano-banana",
    "nano-banana-edit": "nano-banana",
    "nano-banana-pro": "nano-banana-pro",
    "nano-banana-2": "nano-banana-2",
    "nano-banana-2-lite": "nano-banana-2-lite",
    "gpt-image-2-t2i": "gpt-image-2",
    "gpt-image-2-i2i": "gpt-image-2",
    "seedream-5-lite-t2i": "seedream-5.0-lite",
    "seedream-5-lite-i2i": "seedream-5.0-lite",
    "seedream-5-pro-t2i": "seedream-5.0-pro",
    "seedream-5-pro-i2i": "seedream-5.0-pro",
    "seedance-2.0": "seedance-2.0",
    "seedance-2.0-fast": "seedance-2.0-fast",
    "seedance-2.0-mini": "seedance-2.0-mini",
    "seedance-2.5": "seedance-2.5",
    "wan-2.7-t2v": "wan/2-7-text-to-video",
    "wan-2.7-i2v": "wan/2-7-image-to-video",
    "kling-3.0": "kling-v3",
    "kling-motion-2.6": "kling-v2.6-motion-720p",
    "veo-3.1": "veo-3.1-fast",
    "gemini-omni-video": "gemini-omni-flash-video",
}


class NexusGenerationUnsupportedInput(NexusGenerationContractError):
    """Request shape exists in KSU but cannot be represented by Nexus without semantic loss."""



logger = logging.getLogger(__name__)


class NexusGenerationProviderService:
    MODEL_IDS = frozenset(NEXUS_MODEL_MAP)

    @classmethod
    def handles(cls, generation: Generation) -> bool:
        return str((generation.parameters or {}).get("_model_id") or "") in cls.MODEL_IDS

    @staticmethod
    def provider_name(generation: Generation) -> str:
        return "nexus" if NexusGenerationProviderService.handles(generation) else "kie"

    @staticmethod
    def _nexus_reference_url(raw: str) -> str:
        """Return a deterministic URL Nexus can fetch without KIE transport.

        Product-owned relative URLs are expanded against PUBLIC_BASE_URL. Absolute
        HTTP(S) references are kept byte-for-byte so retries with the same Nexus
        Idempotency-Key also keep the exact same request body.
        """

        value = str(raw or "").strip()
        if not value:
            raise NexusGenerationContractError("Nexus reference URL must not be empty")

        parsed = urlsplit(value)
        if parsed.scheme in {"https", "http"} and parsed.netloc:
            return value

        if not (
            ReferenceStaticStorage.is_local_url(value)
            or FeedStaticStorage.is_local_url(value)
        ):
            raise NexusGenerationContractError(
                "Nexus reference must be an absolute URL or product-owned media URL"
            )

        base = urlsplit(settings.public_base_url.strip())
        if base.scheme != "https" or not base.netloc:
            raise NexusGenerationContractError(
                "PUBLIC_BASE_URL must be HTTPS to send stored references to Nexus"
            )
        path = parsed.path or value.split("?", 1)[0]
        return urlunsplit((base.scheme, base.netloc, path, "", ""))

    @classmethod
    def _media_list(
        cls,
        input_data: dict[str, Any],
        *keys: str,
        max_items: int | None = None,
    ) -> list[str]:
        raw: Any = None
        for key in keys:
            value = input_data.get(key)
            if value not in (None, "", []):
                raw = value
                break
        if raw in (None, "", []):
            return []
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        result = list(
            dict.fromkeys(
                cls._nexus_reference_url(str(item).strip())
                for item in values
                if str(item).strip()
            )
        )
        if max_items is not None and len(result) > max_items:
            raise NexusGenerationUnsupportedInput(
                f"Nexus accepts at most {max_items} references for this model"
            )
        return result

    @staticmethod
    def _put_if_present(target: dict[str, Any], source: dict[str, Any], *keys: str) -> None:
        for key in keys:
            value = source.get(key)
            if value not in (None, ""):
                target[key] = value

    @classmethod
    def _normalize_input(cls, model_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        nexus_model = NEXUS_MODEL_MAP.get(model_id)
        if nexus_model is None:
            raise NexusGenerationContractError(f"Unsupported Nexus model: {model_id}")

        prompt = str(input_data.get("prompt") or "").strip()
        if not prompt:
            if model_id == "kling-3.0":
                raise NexusGenerationUnsupportedInput("Kling 3 Nexus requires a prompt")
            raise NexusGenerationContractError("Prompt must not be empty")
        params: dict[str, Any] = {"model_name": nexus_model, "prompt": prompt}

        if model_id.startswith("nano-banana"):
            if model_id in {"nano-banana", "nano-banana-edit"}:
                output_format = str(input_data.get("output_format") or "png").lower()
                if output_format not in {"", "png"}:
                    raise NexusGenerationUnsupportedInput(
                        "Nano Banana output format is not configurable through Nexus"
                    )
            refs = cls._media_list(input_data, "image_input", "image_urls", max_items=4)
            if refs:
                params["image_urls"] = refs
            params["aspect_ratio"] = str(input_data.get("aspect_ratio") or "auto")
            if model_id in {"nano-banana-pro", "nano-banana-2"}:
                params["image_size"] = str(
                    input_data.get("image_size") or input_data.get("resolution") or "1K"
                ).upper()
            return params

        if model_id.startswith("gpt-image-2-"):
            if input_data.get("resolution") not in (None, ""):
                raise NexusGenerationUnsupportedInput(
                    "GPT Image 2 resolution is not configurable through Nexus"
                )
            refs = cls._media_list(input_data, "input_urls", "image_urls", max_items=4)
            if refs:
                params["image_urls"] = refs
            params["aspect_ratio"] = str(input_data.get("aspect_ratio") or "auto")
            return params

        if model_id.startswith("seedream-5-lite-"):
            if input_data.get("aspect_ratio") not in (None, ""):
                raise NexusGenerationUnsupportedInput(
                    "Seedream 5 Lite aspect ratio is not configurable through Nexus"
                )
            if input_data.get("nsfw_checker") is True:
                raise NexusGenerationUnsupportedInput(
                    "Seedream 5 Lite NSFW checker is not configurable through Nexus"
                )
            refs = cls._media_list(input_data, "image_urls", max_items=14)
            if refs:
                params["image_urls"] = refs
            quality = str(input_data.get("quality") or "basic").lower()
            if quality not in {"basic", "high"}:
                raise NexusGenerationUnsupportedInput(
                    "Seedream 5 Lite Ultra/unknown quality is not available through Nexus"
                )
            params["resolution"] = "2K" if quality == "basic" else "3K"
            params["output_format"] = str(input_data.get("output_format") or "png").lower()
            return params

        if model_id.startswith("seedream-5-pro-"):
            if input_data.get("nsfw_checker") is True:
                raise NexusGenerationUnsupportedInput(
                    "Seedream 5 Pro NSFW checker is not configurable through Nexus"
                )
            ratio = str(input_data.get("aspect_ratio") or "1:1")
            if ratio == "21:9":
                raise NexusGenerationUnsupportedInput(
                    "Seedream 5 Pro 21:9 is not available through Nexus"
                )
            refs = cls._media_list(input_data, "image_urls", max_items=10)
            if refs:
                params["image_urls"] = refs
            quality = str(input_data.get("quality") or "basic").lower()
            if quality not in {"basic", "high"}:
                raise NexusGenerationUnsupportedInput(
                    "Unsupported Seedream quality for Nexus"
                )
            params["resolution"] = "1K" if quality == "basic" else "2K"
            params["aspect_ratio"] = ratio
            params["output_format"] = str(input_data.get("output_format") or "png").lower()
            return params

        if model_id.startswith("seedance-"):
            if input_data.get("web_search") is True:
                raise NexusGenerationUnsupportedInput(
                    "Seedance web search is not available through Nexus"
                )
            if model_id == "seedance-2.5":
                if input_data.get("return_last_frame") is True:
                    raise NexusGenerationUnsupportedInput(
                        "Seedance 2.5 return_last_frame is not available through Nexus"
                    )
                output_format = str(input_data.get("output_format") or "mp4").lower()
                if output_format != "mp4":
                    raise NexusGenerationUnsupportedInput(
                        "Seedance 2.5 MOV output is not available through Nexus"
                    )
                if input_data.get("nsfw_checker") not in (None, ""):
                    params["content_filter"] = bool(input_data.get("nsfw_checker"))
            images = cls._media_list(input_data, "reference_image_urls", max_items=30)
            videos = cls._media_list(input_data, "reference_video_urls", max_items=10)
            audios = cls._media_list(input_data, "reference_audio_urls", max_items=10)
            if model_id != "seedance-2.5":
                if len(images) > 9 or len(videos) > 3 or len(audios) > 3:
                    raise NexusGenerationUnsupportedInput(
                        "Seedance 2.0 Nexus reference limit exceeded"
                    )
            if images:
                params["image_urls"] = images
            if videos:
                params["video_urls"] = videos
            if audios:
                params["audio_urls"] = audios
            cls._put_if_present(
                params, input_data, "aspect_ratio", "duration", "resolution", "generate_audio"
            )
            return params

        if model_id == "wan-2.7-t2v":
            duration = int(input_data.get("duration") or 5)
            if not 2 <= duration <= 10:
                raise NexusGenerationUnsupportedInput(
                    "Wan 2.7 Nexus supports duration from 2 to 10 seconds"
                )
            params["duration"] = duration
            for key in (
                "negative_prompt", "resolution", "prompt_extend", "watermark",
                "seed", "audio_url",
            ):
                cls._put_if_present(params, input_data, key)
            ratio = input_data.get("ratio") or input_data.get("aspect_ratio")
            if ratio not in (None, ""):
                params["aspect_ratio"] = ratio
            return params

        if model_id == "wan-2.7-i2v":
            if input_data.get("aspect_ratio") not in (None, ""):
                raise NexusGenerationUnsupportedInput(
                    "Wan 2.7 image-to-video aspect ratio is not configurable through Nexus"
                )
            duration = int(input_data.get("duration") or 5)
            if not 2 <= duration <= 10:
                raise NexusGenerationUnsupportedInput(
                    "Wan 2.7 Nexus supports duration from 2 to 10 seconds"
                )
            params["duration"] = duration
            for key in (
                "negative_prompt", "resolution", "prompt_extend", "watermark", "seed",
                "first_frame_url", "last_frame_url", "first_clip_url", "driving_audio_url",
            ):
                value = input_data.get(key)
                if key.endswith("_url") and value:
                    params[key] = cls._nexus_reference_url(str(value))
                elif value not in (None, ""):
                    params[key] = value
            return params

        if model_id == "kling-3.0":
            if input_data.get("multi_shots") or input_data.get("multi_prompt") or input_data.get("kling_elements"):
                raise NexusGenerationUnsupportedInput(
                    "Kling 3 multi-shot/elements are not available through Nexus"
                )
            if input_data.get("sound"):
                raise NexusGenerationUnsupportedInput(
                    "Kling 3 sound mode is not available through Nexus"
                )
            images = cls._media_list(input_data, "image_urls", max_items=2)
            if len(images) > 1:
                raise NexusGenerationUnsupportedInput(
                    "Kling 3 Nexus accepts one frame image"
                )
            if images:
                params["image_url"] = images[0]
            mode = str(input_data.get("mode") or "").lower()
            if mode == "4k":
                raise NexusGenerationUnsupportedInput(
                    "Kling 3 4K mode is not available through Nexus"
                )
            if mode == "pro":
                params["model_name"] = "kling-v3-pro"
            cls._put_if_present(params, input_data, "duration", "aspect_ratio", "negative_prompt", "seed")
            return params

        if model_id == "kling-motion-2.6":
            images = cls._media_list(input_data, "input_urls", max_items=1)
            videos = cls._media_list(input_data, "video_urls", max_items=1)
            if len(images) != 1 or len(videos) != 1:
                raise NexusGenerationUnsupportedInput(
                    "Kling Motion 2.6 requires one image and one video"
                )
            mode = str(input_data.get("mode") or "720p").lower()
            params["model_name"] = (
                "kling-v2.6-motion-1080p" if mode == "1080p" else "kling-v2.6-motion-720p"
            )
            params["image_url"] = images[0]
            params["video_url"] = videos[0]
            params["character_orientation"] = str(
                input_data.get("character_orientation") or "video"
            )
            params["duration"] = int(input_data.get("duration") or input_data.get("_billing_seconds") or 3)
            return params

        if model_id == "veo-3.1":
            if str(input_data.get("watermark_text") or "").strip():
                raise NexusGenerationUnsupportedInput(
                    "Veo watermark text is not available through Nexus"
                )
            variant = str(input_data.get("veo_model") or "veo3_fast")
            variants = {
                "veo3_lite": "veo-3.1-lite",
                "veo3_fast": "veo-3.1-fast",
                "veo3_fast_r2v": "veo-3.1-fast",
                "veo3": "veo-3.1-quality",
                "veo3_r2v": "veo-3.1-quality",
            }
            if variant not in variants:
                raise NexusGenerationUnsupportedInput("Unsupported Veo 3.1 Nexus variant")
            params["model_name"] = variants[variant]
            images = cls._media_list(input_data, "image_urls", max_items=3)
            if images:
                generation_type = str(input_data.get("generation_type") or "")
                if generation_type == "FIRST_AND_LAST_FRAMES_2_VIDEO" and len(images) >= 2:
                    params["image_url"], params["last_image_url"] = images[:2]
                elif len(images) == 1:
                    params["image_url"] = images[0]
                else:
                    params["image_urls"] = images
            duration = int(input_data.get("duration") or input_data.get("_billing_seconds") or 8)
            if duration not in {4, 6, 8}:
                raise NexusGenerationUnsupportedInput(
                    "Veo 3.1 Nexus supports duration 4, 6 or 8 seconds"
                )
            params["duration"] = duration
            resolution = str(input_data.get("resolution") or "720p")
            params["resolution"] = resolution.lower() if resolution.lower() != "4k" else "4k"
            ratio = str(input_data.get("aspect_ratio") or "16:9")
            if ratio.lower() != "auto":
                params["aspect_ratio"] = ratio
            return params

        if model_id == "gemini-omni-video":
            if input_data.get("audio_ids") or input_data.get("video_list") or input_data.get("character_ids"):
                raise NexusGenerationUnsupportedInput(
                    "Gemini Omni media IDs/video references require the existing Kie path"
                )
            images = cls._media_list(input_data, "image_urls", max_items=7)
            if images:
                params["reference_image_urls"] = images
            duration = int(input_data.get("duration") or 4)
            if duration not in {4, 6, 8, 10}:
                raise NexusGenerationUnsupportedInput(
                    "Gemini Omni Nexus supports duration 4, 6, 8 or 10 seconds"
                )
            params["duration"] = duration
            cls._put_if_present(params, input_data, "aspect_ratio", "resolution", "seed")
            return params

        raise NexusGenerationContractError(f"Unsupported Nexus model: {model_id}")

    @staticmethod
    def _error_disposition(exc: Exception) -> str:
        if isinstance(exc, NexusGenerationContractError):
            return "permanent"
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status == 429:
                return "retryable"
            if 400 <= status < 500 and status not in {408, 425}:
                return "permanent"
            return "uncertain"
        if isinstance(exc, (httpx.TransportError, json.JSONDecodeError)):
            return "uncertain"
        if isinstance(exc, NexusProviderError):
            message = str(exc).lower()
            if (
                "not configured" in message
                or "unsupported" in message
                or "must not be empty" in message
                or "at most" in message
            ):
                return "permanent"
            return "uncertain"
        return "permanent"

    @classmethod
    async def _record_submission_error(
        cls,
        session: AsyncSession,
        generation_id: uuid.UUID,
        exc: Exception,
    ) -> None:
        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            generation is None or generation.provider != "nexus"
            or generation.status in {"succeeded", "failed"} or generation.external_id
        ):
            return
        disposition = cls._error_disposition(exc)
        if isinstance(exc, NexusGenerationUnsupportedInput):
            fallback = await switch_to_fallback(
                session,
                generation_id,
                reason=f"Nexus request shape unsupported: {exc}",
                expected_provider="nexus",
            )
            if fallback is not None:
                return
        # Only explicit pre-task availability rejections permit a new provider.
        # Transport errors/5xx may hide an accepted, chargeable Nexus task.
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {401, 402, 404, 429}:
            fallback = await switch_to_fallback(
                session, generation_id, reason=f"Nexus HTTP {exc.response.status_code}",
                expected_provider="nexus",
            )
            if fallback is not None:
                return
        if (generation.parameters or {}).get("_submission_uncertain"):
            disposition = "uncertain"
        if disposition == "permanent":
            await GenerationProviderService.fail_and_refund(session, generation_id, str(exc))
            return

        now = datetime.now(timezone.utc)
        # Nexus caches successful /generate responses by Idempotency-Key for 24h.
        # Requeue uncertain outcomes so the durable worker safely replays the exact
        # same logical request and recovers the original task_id instead of waiting
        # for a callback that image tasks do not require.
        generation.status = "retry"
        generation.error = f"Nexus submission {disposition}: {exc}"[:4000]
        generation.updated_at = now
        generation.provider = "nexus"
        parameters = dict(generation.parameters or {})
        if disposition == "uncertain":
            parameters["_submission_uncertain"] = True
            parameters.setdefault("_submission_uncertain_at", now.isoformat())
        else:
            parameters.pop("_submission_uncertain", None)
            parameters.pop("_submission_uncertain_at", None)
        generation.parameters = parameters
        await session.commit()

    @classmethod
    async def submit(cls, session: AsyncSession, generation_id: uuid.UUID) -> Generation:
        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if generation is None:
            raise LookupError("Generation not found")
        if generation.status not in {"queued", "retry"}:
            return generation
        if generation.external_id or (
            (generation.parameters or {}).get("_provider_route") and generation.provider != "nexus"
        ):
            return generation
        if not cls.handles(generation):
            raise NexusGenerationContractError("Generation is not routed to Nexus")

        model_id = str((generation.parameters or {}).get("_model_id") or "")
        generation.provider = "nexus"
        generation.status = "submitting"
        generation.error = None
        await session.commit()

        try:
            input_data = GenerationProviderService._input_for(generation)
            billing_seconds = (generation.parameters or {}).get("_billing_seconds")
            if billing_seconds not in (None, ""):
                input_data["_billing_seconds"] = billing_seconds
            normalized = cls._normalize_input(model_id, input_data)

            logger.info(
                "nexus_submit submitting gen=%s model=%s references=%s",
                generation_id, model_id, len(normalized.get("image_urls") or []),
            )

            client = NexusClient(settings.nexus_api_key, settings.nexus_api_base_url)
            try:
                task_id = await client.create_generation(
                    params=normalized,
                    idempotency_key=f"generation:{generation.id}",
                )
            finally:
                await client.aclose()
        except Exception as exc:
            await cls._record_submission_error(session, generation.id, exc)
            refreshed = await session.get(Generation, generation.id)
            if refreshed is not None and (
                refreshed.provider != "nexus" or refreshed.external_id
                or refreshed.status == "succeeded"
            ):
                return refreshed
            raise

        generation = await session.scalar(
            select(Generation).where(Generation.id == generation_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if generation is None:
            raise LookupError("Generation disappeared after Nexus submission")
        if generation.provider != "nexus" or generation.status in {"succeeded", "failed"}:
            return generation
        if generation.external_id and generation.external_id != task_id:
            return generation

        now = datetime.now(timezone.utc)
        generation.external_id = task_id
        generation.provider = "nexus"
        generation.status = "generating"
        generation.error = None
        generation.updated_at = now
        GenerationProviderService._mark_provider_task_bound(generation, now=now)
        await session.commit()
        return generation

    @classmethod
    async def sync_task(
        cls,
        session: AsyncSession,
        *,
        task_id: str,
        generation_id: uuid.UUID | None = None,
    ) -> Generation | None:
        generation = await session.scalar(
            select(Generation)
            .where(Generation.provider == "nexus", Generation.external_id == task_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if generation is None and generation_id is not None:
            candidate = await session.scalar(
                select(Generation).where(Generation.id == generation_id).with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                candidate is not None
                and candidate.external_id == task_id
                and candidate.provider == "nexus"
            ):
                generation = candidate
        if generation is None or generation.status in {"succeeded", "failed"}:
            return generation

        client = NexusClient(settings.nexus_api_key, settings.nexus_api_base_url)
        try:
            task = await client.get_task(task_id)
        finally:
            await client.aclose()

        if task.status == "completed" and not task.image_urls:
            generation.status = "generating"
            generation.error = "Nexus reported completed without result URLs; awaiting reconciliation"
            generation.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return generation

        state = (
            "success"
            if task.status == "completed"
            else "fail"
            if task.status == "failed"
            else task.status
        )
        if task.status == "failed":
            # Generic failure and content-policy rejection are not proof of a
            # technical outage. Only explicitly technical terminal failures retry.
            reason = str(task.error or "").lower()
            policy = any(word in reason for word in (
                "policy", "copyright", "moderation", "safety", "nsfw",
                "forbidden content", "content violation",
            ))
            technical = any(word in reason for word in ("timeout", "timed out", "unavailable", "internal server error"))
            if technical and not policy:
                fallback = await switch_to_fallback(
                    session, generation.id, reason="Nexus terminal technical failure",
                    expected_provider="nexus", terminal_failure=True,
                )
                if fallback is not None:
                    return fallback
        logger.info(
            "nexus_sync_task gen=%s task=%s nexus_status=%s state=%s urls=%s",
            generation_id, task_id, task.status, state,
            f"count={len(task.image_urls)}" if task.image_urls else "none",
        )
        provider_task = KieTask(
            task_id=task.task_id,
            state=state,
            result_urls=task.image_urls,
            fail_code="nexus_failed" if task.status == "failed" else "",
            fail_message=task.error or ("Nexus generation failed" if task.status == "failed" else ""),
            raw=task.raw,
        )
        await GenerationProviderService.apply_kie_task(session, generation, provider_task)
        return generation
