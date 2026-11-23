"""Public ROXY landing must show *real* active trends, not concept art or private recipes."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_redis
from app.api.v1 import public_site
from app.db.session import get_session
from app.main import app
from app.services.trends import TrendService


class FakeScalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.queries = 0

    async def scalars(self, query):
        self.queries += 1
        return FakeScalars(self.rows)


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        assert ex == public_site.CACHE_SECONDS
        self.data[key] = value


def trend(n: int, *, usages: object, url: str | None, active: bool = True):
    return SimpleNamespace(
        id=uuid.UUID(int=n),
        title="Тренд " + str(n),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=n),
        is_active=active,
        payload={"usage_count": usages, "preview_url": url, "prompt": "SECRET NEVER PUBLIC"},
    )


@pytest.mark.parametrize(
    ("url", "valid"),
    [
        ("https://cdn.example.org/media/trend.mp4", True),
        ("https://cdn.example.org/media/photo.webp", True),
        ("http://127.0.0.1:8080/private.mp4", False),
        ("http://localhost:8000/foo.png", False),
        ("https://192.168.1.1/file.mp4", False),
        ("https://10.0.0.8/private", False),
        ("https://user:pass@cdn.example.org/image.jpg", False),
        ("javascript:alert(1)", False),
        ("data:image/png,evil", False),
        ("//evil.example.org/trend.mp4", False),
        ("http://cdn.example.org/video.mp4", False),
        ("", False),
    ],
)
def test_public_trend_preview_urls_are_safe(url, valid):
    assert (public_site._safe_preview_url(url) is not None) is valid


@pytest.mark.asyncio
async def test_popular_trends_sort_by_real_counter_and_hide_private_recipes(monkeypatch):
    rows = [
        trend(1, usages=15, url="https://cdn.example.org/media/portrait.webp"),
        trend(2, usages=600, url="https://cdn.example.org/media/motion.mp4"),
        trend(3, usages=0, url="https://cdn.example.org/media/cat.jpg"),
        trend(4, usages=800, url=None),
        trend(5, usages="not_a_number", url="https://cdn.example.org/media/unknown.png"),
    ]
    session = FakeSession(rows)

    async def public_view(_session, item):
        assert item.is_active
        return {
            "id": str(item.id),
            "title": item.title,
            "preview_url": item.payload["preview_url"],
            "media_type": "video" if item.id.int == 2 else "image",
            "preview_thumbnail_url": None,
            "prompt": "SECRET NEVER PUBLIC",
            "parameters": {"provider_key": "DO NOT LEAK"},
        }

    monkeypatch.setattr(TrendService, "public_view", public_view)
    payload = await public_site.popular_trends_payload(session, limit=6)
    assert [item["id"] for item in payload["items"]] == [
        str(uuid.UUID(int=n)) for n in (2, 1, 3, 5)
    ]
    assert payload["items"][0]["preview_kind"] == "video"
    assert payload["items"][0]["usage_count"] == 600
    assert payload["items"][1]["preview_kind"] == "image"
    assert "prompt" not in str(payload)
    assert "provider_key" not in str(payload)
    assert session.queries == 1


@pytest.mark.asyncio
async def test_public_site_trends_route_works_anonymously_and_uses_cache(monkeypatch):
    rows = [trend(10, usages=14, url="https://cdn.example.org/t-10.mp4")]
    session, redis = FakeSession(rows), FakeRedis()

    async def public_view(_session, row):
        return {
            "title": row.title,
            "media_type": "video",
            "preview_url": row.payload["preview_url"],
            "preview_thumbnail_url": None,
        }

    monkeypatch.setattr(TrendService, "public_view", public_view)

    async def session_override():
        yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_redis] = lambda: redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.get("/api/v1/public-site/popular-trends?limit=6")
            second = await client.get("/api/v1/public-site/popular-trends?limit=1")
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_redis, None)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["items"][0]["title"] == "Тренд 10"
    assert first.json()["items"][0]["preview_kind"] == "video"
    assert first.json()["ranking"] == "usage_count"
    assert "public, max-age=" in first.headers["cache-control"]
    assert session.queries == 1


@pytest.mark.asyncio
async def test_empty_trends_returns_empty_items_not_illustrative_fake_fallback(monkeypatch):
    session = FakeSession([])
    result = await public_site.popular_trends_payload(session)
    assert result["items"] == []
