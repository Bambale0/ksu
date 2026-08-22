from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "mini-app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_active_mini_app_uses_fresh_drafts_by_default_and_explicit_reuse() -> None:
    page = _read(FRONTEND / "app" / "page.tsx")
    app = _read(FRONTEND / "components" / "roxy-social-app.tsx")
    api = _read(FRONTEND / "lib" / "api.ts")

    assert "RoxySocialApp" in page
    assert "DRAFTS_KEY" not in app
    assert "createDefaultDraft(target)" in app
    assert 'kind: "new"' in app
    assert 'kind: "reuse"' in app
    assert "hydrateReuseDraft" in app
    assert "Использовать настройки" in app
    assert "api.recreateGeneration" in app
    assert '/generations/${encodeURIComponent(id)}/recreate' in api


def test_generation_result_deep_link_and_background_copy_are_present() -> None:
    app = _read(FRONTEND / "components" / "roxy-social-app.tsx")

    assert 'searchParams.get("generation")' in app
    assert 'setPreviewSurface("private")' in app
    assert 'setRoute("history")' in app
    assert "ROXY можно закрыть — результат придёт в Telegram" in app


def test_bottom_navigation_labels_are_forced_to_one_line() -> None:
    css = _read(FRONTEND / "app" / "ux-polish.css")
    assert ".bottom-nav button small" in css
    assert "white-space: nowrap" in css
    assert "text-overflow: ellipsis" in css


def test_generation_model_tracks_telegram_delivery_fields() -> None:
    models = _read(ROOT / "app" / "db" / "models.py")
    migration = _read(ROOT / "alembic" / "versions" / "0028_generation_telegram_delivery.py")
    worker = _read(ROOT / "app" / "workers" / "notifications.py")

    for token in (
        "telegram_notification_status",
        "telegram_notification_sent_at",
        "telegram_message_id",
    ):
        assert token in models
        assert token in migration
        assert token in worker
    assert "send_photo" in worker
    assert "send_video" in worker
    assert "🚀 Открыть в ROXY" in worker
    assert "📥 Скачать оригинал" in worker
