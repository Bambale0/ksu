from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "mini-app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_active_mini_app_uses_fresh_drafts_by_default_and_explicit_reuse() -> None:
    page = _read(FRONTEND / "app" / "page.tsx")
    entry_gate = _read(FRONTEND / "components" / "app-entry-gate.tsx")
    app = _read(FRONTEND / "components" / "roxy-social-app.tsx")
    action_app = _read(FRONTEND / "components" / "generation-action-app.tsx")
    api = _read(FRONTEND / "lib" / "api.ts")

    assert "AppEntryGate" in page
    assert "GenerationActionGate" in entry_gate
    assert "FeedStartApp" in entry_gate
    assert "RoxySocialApp" in action_app
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
    action_app = _read(FRONTEND / "components" / "generation-action-app.tsx")
    worker = _read(ROOT / "app" / "workers" / "notifications.py")

    assert 'searchParams.get("generation")' in app
    assert 'setPreviewSurface("private")' in app
    assert 'setRoute("history")' in app
    assert "ROXY можно закрыть — результат придёт в Telegram" in app
    assert 'route=generation-action' not in worker  # URL is built structurally, not as an unsafe literal.
    assert '"route": "generation-action" if action else "history"' in worker
    assert 'searchParams.get("action")' in action_app
    assert '/action-context?action=' in action_app


def test_bottom_navigation_labels_are_forced_to_one_line() -> None:
    css = _read(FRONTEND / "app" / "ux-polish.css")
    assert ".bottom-nav button small" in css
    assert "white-space: nowrap" in css
    assert "text-overflow: ellipsis" in css


def test_generation_model_tracks_telegram_delivery_fields() -> None:
    models = _read(ROOT / "app" / "db" / "models.py")
    migration = _read(ROOT / "alembic" / "versions" / "0028_generation_telegram_delivery.py")
    worker = _read(ROOT / "app" / "workers" / "notifications.py")
    media = _read(ROOT / "app" / "services" / "telegram_generation_media.py")

    for token in (
        "telegram_notification_status",
        "telegram_notification_sent_at",
        "telegram_message_id",
    ):
        assert token in models
        assert token in migration
        assert token in worker

    # The notification worker owns durable delivery state and delegates the
    # media transport to one hardened service. That service must preserve the
    # native photo/video/audio paths plus the exact-file document fallback.
    assert "send_generation_result_media" in worker
    assert "send_photo" in media
    assert "send_video" in media
    assert "send_audio" in media
    assert "send_document" in media
    assert "🚀 Открыть в ROXY" in worker
    assert "📥 Скачать оригинал" in worker


def test_lena_style_actions_are_delivered_with_result_and_live_in_mini_app() -> None:
    worker = _read(ROOT / "app" / "workers" / "notifications.py")
    service = _read(ROOT / "app" / "services" / "generation_actions" / "core.py")
    api = _read(ROOT / "app" / "api" / "v1" / "generation_actions.py")
    action_app = _read(FRONTEND / "components" / "generation-action-app.tsx")

    for label in (
        "✨ Ремикс",
        "🔁 Ещё вариант",
        "💅 Изменить образ",
        "🎬 Оживить",
        "✏️ Новый промпт",
        "⚙️ Изменить параметры",
        "📤 Опубликовать",
    ):
        assert label in service
    assert "GenerationActionService.available_actions" in worker
    assert 'web_app=WebAppInfo(url=action_url)' in worker
    assert '@router.get("/{generation_id}/action-context")' in api
    assert '@router.post("/{generation_id}/actions/{action}"' in api
    assert 'parent_generation_id=parent.id' in api
    assert 'action_type=canonical' in api
    assert "SavedReferencePicker" in action_app
    assert "grok-video-i2v" in service
