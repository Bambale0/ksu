from __future__ import annotations

from pathlib import Path

from app.api.v1.inline_social_admin import router


def test_inline_social_admin_routes_are_registered() -> None:
    routes = {(route.path, frozenset(route.methods or set())) for route in router.routes}
    assert any(
        path == "/inline-admin/feed/{generation_id}/moderation" and "POST" in methods
        for path, methods in routes
    )
    assert any(
        path == "/inline-admin/trends/{trend_id}" and "DELETE" in methods
        for path, methods in routes
    )


def test_mini_app_exposes_live_trends_and_admin_moderation_controls() -> None:
    page = Path("frontend/mini-app/app/page.tsx").read_text(encoding="utf-8")
    trends = Path("frontend/mini-app/components/live-trend-rail.tsx").read_text(encoding="utf-8")
    media = Path("frontend/mini-app/components/trend-preview-media.tsx").read_text(encoding="utf-8")
    moderation = Path("frontend/mini-app/components/feed-admin-moderation.tsx").read_text(encoding="utf-8")

    catalog = Path("frontend/mini-app/components/catalog-route-features.tsx").read_text(encoding="utf-8")
    feed = Path("frontend/mini-app/components/feed-route-features.tsx").read_text(encoding="utf-8")
    assert "<AppEntryGate />" in page
    assert "<LiveTrendRail {...props} />" in catalog
    assert "<FeedAdminModeration />" in feed
    assert "Актуальные тренды" in trends
    assert "<TrendPreviewMedia" in trends
    assert "autoPlay" in media and "loop" in media and "playsInline" in media
    assert "Удалить" in trends
    assert 'apply("blurred")' in moderation
    assert 'apply("hidden")' in moderation
    assert 'apply("removed")' in moderation
    assert 'apply("visible")' in moderation


def test_trend_page_renders_video_previews_as_video() -> None:
    source = Path("frontend/mini-app/app/trend/page.tsx").read_text(encoding="utf-8")
    assert "previewIsVideo" in source
    assert '<video className="trend-preview"' in source
    assert "autoPlay loop playsInline controls" in source
