from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any
from urllib.parse import urlsplit

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.providers.kie_pinterest_analysis import (
    KiePinterestAnalysisClient,
    PinterestSceneAnalysisProviderError,
)
from app.services.abuse_protection import AbuseProtectionService
from app.services.provider_media_transport import (
    ProviderMediaTransport,
    ProviderMediaTransportError,
)

logger = logging.getLogger(__name__)


class PinterestSceneAnalysisError(RuntimeError):
    pass


class PinterestSceneAnalysisService:
    CACHE_TTL_SECONDS = 24 * 60 * 60
    MAX_TEXT_LENGTH = 800
    MAX_PRESERVE_ITEMS = 10
    MAX_PRESERVE_ITEM_LENGTH = 240
    TEXT_FIELDS = (
        "scene",
        "composition",
        "camera",
        "pose",
        "lighting",
        "environment",
        "wardrobe",
        "expression",
        "gaze",
    )

    @staticmethod
    def _clean_image_url(value: str) -> str:
        cleaned = value.strip()
        parsed = urlsplit(cleaned)
        if (
            len(cleaned) < 8
            or len(cleaned) > 4096
            or parsed.scheme != "https"
            or not parsed.netloc
        ):
            raise PinterestSceneAnalysisError("Референс должен быть публичной HTTPS-ссылкой")
        return cleaned

    @classmethod
    def _cache_key(cls, user_id: uuid.UUID, image_url: str) -> str:
        digest = hashlib.sha256(image_url.encode("utf-8")).hexdigest()
        return f"pinterest-repeat:analysis:{user_id}:{digest}"

    @classmethod
    def _normalize(cls, raw: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field in cls.TEXT_FIELDS:
            value = str(raw.get(field) or "").strip()
            if not value:
                raise PinterestSceneAnalysisError(f"AI-анализ не вернул поле {field}")
            result[field] = value[: cls.MAX_TEXT_LENGTH]

        preserve_raw = raw.get("must_preserve")
        if not isinstance(preserve_raw, list):
            raise PinterestSceneAnalysisError("AI-анализ вернул неверный must_preserve")
        preserve: list[str] = []
        for item in preserve_raw[: cls.MAX_PRESERVE_ITEMS]:
            clean = str(item or "").strip()
            if clean:
                preserve.append(clean[: cls.MAX_PRESERVE_ITEM_LENGTH])
        result["must_preserve"] = preserve
        return result

    @classmethod
    async def analyze(
        cls,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        image_url: str,
    ) -> tuple[dict[str, Any], str, bool]:
        clean_url = cls._clean_image_url(image_url)
        cache_key = cls._cache_key(user_id, clean_url)
        try:
            cached = await redis.get(cache_key)
        except RedisError:
            cached = None
        if cached:
            try:
                decoded = cached.decode("utf-8") if isinstance(cached, bytes) else str(cached)
                payload = json.loads(decoded)
                if isinstance(payload, dict):
                    normalized = cls._normalize(payload.get("analysis") or {})
                    model = str(payload.get("model") or KiePinterestAnalysisClient.MODEL)
                    return normalized, model, True
            except (ValueError, TypeError, json.JSONDecodeError, PinterestSceneAnalysisError):
                logger.warning("Ignoring invalid Pinterest analysis cache entry for %s", user_id)

        await AbuseProtectionService.consume(
            redis,
            key=f"abuse:pinterest-repeat-analysis:user:{user_id}",
            limit=max(1, settings.generation_rate_limit_per_minute),
            window_seconds=60,
            message="Pinterest scene analysis rate limit exceeded",
        )
        await AbuseProtectionService.provider_submission_gate(redis, "kie-pinterest-repeat-analysis")

        try:
            provider_input = await ProviderMediaTransport.prepare({"image_url": clean_url})
            provider_url = str(provider_input.get("image_url") or "").strip()
            if not provider_url:
                raise PinterestSceneAnalysisError("Не удалось подготовить референс для AI-анализа")

            client = KiePinterestAnalysisClient(settings.kie_api_key, settings.kie_base_url)
            try:
                provider_result = await client.analyze(image_url=provider_url)
            finally:
                await client.aclose()
            analysis = cls._normalize(provider_result.payload)
            await AbuseProtectionService.record_provider_success(redis, "kie-pinterest-repeat-analysis")
        except PinterestSceneAnalysisError:
            await AbuseProtectionService.record_provider_failure(redis, "kie-pinterest-repeat-analysis")
            raise
        except (PinterestSceneAnalysisProviderError, ProviderMediaTransportError) as exc:
            await AbuseProtectionService.record_provider_failure(redis, "kie-pinterest-repeat-analysis")
            raise PinterestSceneAnalysisError("Не удалось разобрать сцену референса") from exc
        except Exception as exc:
            await AbuseProtectionService.record_provider_failure(redis, "kie-pinterest-repeat-analysis")
            logger.exception("Pinterest scene analysis failed for user %s", user_id)
            raise PinterestSceneAnalysisError("Не удалось разобрать сцену референса") from exc

        cache_payload = json.dumps(
            {"analysis": analysis, "model": provider_result.model},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            await redis.setex(cache_key, cls.CACHE_TTL_SECONDS, cache_payload)
        except RedisError:
            logger.warning("Pinterest analysis cache write failed for %s", user_id)
        return analysis, provider_result.model, False
