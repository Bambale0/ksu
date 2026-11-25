"""Public read-only popular-trend projection for independent ROXY landing.

Only presentation fields of active, validated curated trends are exposed.
This endpoint never requires Telegram auth, reads private recipes into neither
JSON nor logs, and never returns source generation/private user data.
"""
from __future__ import annotations

import ipaddress
import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from fastapi import APIRouter, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RedisDep, SessionDep
from app.core.config import settings
from app.db.admin_models import AdminTrend
from app.services.trends import TrendService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public-site", tags=["public-site"])
CACHE_KEY = "roxy:public-site:popular-trends:v2"
CACHE_SECONDS = 90
VIDEO_SUFFIXES = (".mp4", ".webm", ".m4v", ".mov")


def _count(payload: dict[str, object]) -> int:
    """An untrusted or administrator-edited counter must never break the gallery."""
    try:
        return min(2_147_483_647, max(0, int(payload.get("usage_count") or 0)))
    except (ValueError, TypeError, OverflowError):
        return 0


def _safe_preview_url(value: object) -> str | None:
    """Allow public HTTPS assets or the application's own uploaded media.

    Avoid reflecting browser-unsafe hosts, malformed schemes and local IPs.
    Local uploads are returned as same-origin paths, not a hardcoded domain.
    """
    url = str(value or "").strip()
    if not url or len(url) > 4000:
        return None
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        if parsed.port is not None and parsed.port not in {80, 443}:
            return None
        hostname = parsed.hostname.strip(".").lower()
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith((".localhost", ".local", ".internal")):
            return None
        try:
            if not ipaddress.ip_address(hostname).is_global:
                return None
        except ValueError:
            pass
        public = urlsplit(settings.public_base_url)
        if public.hostname and hostname == public.hostname.lower() and parsed.path.startswith("/uploads/refs/"):
            # Existing public uploads are already mounted by KSU.
            return parsed.path + ("?" + parsed.query if parsed.query else "")
        if parsed.scheme != "https":
            return None
        return url
    except (ValueError, UnicodeError):
        return None


async def popular_trends_payload(session: AsyncSession, *, limit: int = 12) -> dict[str, object]:
    rows = (await session.scalars(select(AdminTrend).where(AdminTrend.is_active.is_(True)))).all()
    # usage_count is the existing server-side per-trend launch counter.
    # Admins may also edit this counter; this is not independently audited analytics.
    ranked = sorted(
        (
            row for row in rows
            if isinstance(row.payload, dict) and _safe_preview_url(row.payload.get("preview_url"))
        ),
        key=lambda row: (_count(row.payload), row.created_at),
        reverse=True,
    )

    items: list[dict[str, object]] = []
    for row in ranked:
        if len(items) >= limit:
            break
        try:
            # Reuse the same validation and public/active visibility contract as
            # the authenticated trend catalog. Never expose the recipe itself.
            view = await TrendService.public_view(session, row)
        except (KeyError, TypeError, ValueError, LookupError) as exc:
            logger.debug("public_site_trend_skipped trend_id=%s cause=%s", row.id, type(exc).__name__)
            continue
        preview_url = _safe_preview_url(view.get("preview_url"))
        if preview_url is None:
            continue
        source_path = urlsplit(preview_url).path.lower()
        kind = "video" if source_path.endswith(VIDEO_SUFFIXES) else "image"
        thumb = view.get("preview_thumbnail_url")
        thumbnail = _safe_preview_url(thumb) if thumb else None
        # Thumbnail routes are relative and intentionally public.
        if isinstance(thumb, str) and thumb.startswith(f"/api/v1/trends/{row.id}/preview-thumbnail"):
            thumbnail = thumb
        # Public catalogue estimates are already calculated by the same recipe
        # service. Sequential workflows expose the FIRST step, not the total.
        cost = None
        try:
            value = Decimal(str(view.get("cost_credits")))
            if value.is_finite() and 0 < value <= Decimal("1000000000"):
                cost = format(value, ".2f")
        except (InvalidOperation, ValueError, TypeError):
            pass
        items.append({
            "catalog_cost_rox": cost,
            "catalog_cost_kind": ("first_step" if view.get("workflow_type") else "estimate") if cost else None,
            "id": str(row.id),
            "title": str(view["title"])[:80],
            "media_type": view.get("media_type", "image"),
            "preview_kind": kind,
            "preview_url": preview_url,
            "poster_url": thumbnail,
            "usage_count": _count(row.payload),
        })
    return {"items": items, "ranking": "usage_count", "updated": "dynamic"}


@router.get("/popular-trends")
async def list_popular_trends(
    response: Response,
    session: SessionDep,
    redis: RedisDep,
    limit: int = Query(default=6, ge=1, le=12),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=60"
    try:
        cached = await redis.get(CACHE_KEY)
        if cached:
            data = json.loads(cached)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return {**data, "items": data["items"][:limit]}
    except Exception:
        logger.warning("public_site_trends_cache_read_failed")

    result = await popular_trends_payload(session, limit=12)
    try:
        await redis.set(CACHE_KEY, json.dumps(result, ensure_ascii=False), ex=CACHE_SECONDS)
    except Exception:
        logger.warning("public_site_trends_cache_write_failed")
    return {**result, "items": result["items"][:limit]}
