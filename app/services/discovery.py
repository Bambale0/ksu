from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import CmsDocument, CmsDocumentVersion


class DiscoveryService:
    HOME_PROMOS_SLUG = "roxy-home-promos"
    MAX_SLIDES = 8
    ALLOWED_ROUTE_TARGETS = frozenset({"home", "catalog", "create", "history", "profile", "wallet"})

    DEFAULT_SLIDES: tuple[dict[str, Any], ...] = (
        {
            "id": "creator-partnership",
            "eyebrow": "Зарабатывай с ROXY",
            "title": "Партнёрская программа",
            "body": "Для авторов и каналов: индивидуальные условия сотрудничества и ежемесячные ROX после согласования.",
            "cta": "Узнать условия",
            "action": {"type": "route", "target": "profile"},
            "image_url": None,
        },
        {
            "id": "create-content",
            "eyebrow": "AI Creative Studio",
            "title": "Создавай фото и видео",
            "body": "Выбери формат, модель и настройки — ROXY соберёт рабочий сценарий генерации.",
            "cta": "Создать",
            "action": {"type": "route", "target": "create"},
            "image_url": None,
        },
        {
            "id": "discover",
            "eyebrow": "Каталог",
            "title": "Шаблоны, тренды и работы сообщества",
            "body": "Начни с готовой идеи или посмотри, что создают другие пользователи ROXY.",
            "cta": "Открыть каталог",
            "action": {"type": "route", "target": "catalog"},
            "image_url": None,
        },
    )

    @classmethod
    def _clean_text(cls, value: Any, *, limit: int, fallback: str = "") -> str:
        text = str(value or "").strip()
        if not text:
            return fallback
        return text[:limit]

    @classmethod
    def _normalize_action(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {"type": "route", "target": "catalog"}
        action_type = str(value.get("type") or "route").strip().lower()
        target = str(value.get("target") or "").strip()
        if action_type == "route" and target in cls.ALLOWED_ROUTE_TARGETS:
            return {"type": "route", "target": target}
        if action_type == "trends":
            return {"type": "trends", "target": "trends"}
        return {"type": "route", "target": "catalog"}

    @classmethod
    def _normalize_slide(cls, raw: Any, index: int) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        title = cls._clean_text(raw.get("title"), limit=120)
        if not title:
            return None
        image_url = cls._clean_text(raw.get("image_url"), limit=2048) or None
        if image_url is not None and not image_url.startswith("https://"):
            image_url = None
        return {
            "id": cls._clean_text(raw.get("id"), limit=80, fallback=f"slide-{index + 1}"),
            "eyebrow": cls._clean_text(raw.get("eyebrow"), limit=80, fallback="ROXY"),
            "title": title,
            "body": cls._clean_text(raw.get("body"), limit=280),
            "cta": cls._clean_text(raw.get("cta"), limit=60, fallback="Открыть"),
            "action": cls._normalize_action(raw.get("action")),
            "image_url": image_url,
        }

    @classmethod
    def normalize_slides(cls, payload: Any) -> list[dict[str, Any]]:
        raw_slides = payload.get("slides") if isinstance(payload, dict) else None
        if not isinstance(raw_slides, list):
            return []
        slides: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_slides[: cls.MAX_SLIDES]):
            normalized = cls._normalize_slide(raw, index)
            if normalized is not None:
                slides.append(normalized)
        return slides

    @classmethod
    async def _published_promos(cls, session: AsyncSession) -> list[dict[str, Any]]:
        document = await session.scalar(
            select(CmsDocument).where(
                CmsDocument.slug == cls.HOME_PROMOS_SLUG,
                CmsDocument.status == "published",
            )
        )
        if document is None:
            return []
        version = await session.scalar(
            select(CmsDocumentVersion)
            .where(
                CmsDocumentVersion.document_id == document.id,
                CmsDocumentVersion.status == "published",
            )
            .order_by(CmsDocumentVersion.published_at.desc().nullslast(), CmsDocumentVersion.version.desc())
            .limit(1)
        )
        if version is None:
            return []
        try:
            payload = json.loads(version.body)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        return cls.normalize_slides(payload)

    @classmethod
    async def home(cls, session: AsyncSession) -> dict[str, Any]:
        slides = await cls._published_promos(session)
        source = "cms" if slides else "default"
        if not slides:
            slides = [dict(item) for item in cls.DEFAULT_SLIDES]
        return {
            "slides": slides,
            "source": source,
            "cms_slug": cls.HOME_PROMOS_SLUG,
            "catalog": {
                "supports": ["trends", "community_feed", "prompt_tools"],
                "feed_media": ["image", "video"],
            },
        }
