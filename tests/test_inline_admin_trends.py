from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "mini-app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_inline_trend_admin_is_mounted_in_customer_mini_app() -> None:
    page = _read(FRONTEND / "app" / "page.tsx")
    component = _read(FRONTEND / "components" / "inline-trend-admin.tsx")

    assert 'import { InlineTrendAdmin } from "@/components/inline-trend-admin"' in page
    assert "<InlineTrendAdmin />" in page
    assert "me.is_admin" in component
    assert 'node.textContent?.trim() === "Готовые сценарии"' in component
    assert "＋ Добавить" in component
    assert "＋ Новый тренд" in component
    assert "Редактировать" in component
    assert "Дублировать" in component
    assert "Скрыть" in component
    assert "Вернуть" in component


def test_inline_trend_admin_supports_durable_preview_upload_and_full_recipe() -> None:
    component = _read(FRONTEND / "components" / "inline-trend-admin.tsx")
    client = _read(FRONTEND / "lib" / "trend-admin-api.ts")
    uploads = _read(ROOT / "app" / "api" / "v1" / "uploads.py")

    assert "await api.upload(file)" in component
    assert 'accept="image/*,video/*"' in component
    assert "Скрытый промпт" in component
    assert "input_mode" in component
    assert "min_references" in component
    assert "max_references" in component
    assert "billing_seconds" in component
    assert "sort_order" in component
    assert "Дополнительные параметры модели" in component
    assert '"/api/v1/trends/manage"' in client
    assert 'method: "PATCH"' in client
    assert 'method: "DELETE"' in client
    assert "/activate" in client
    assert '"Idempotency-Key"' in client
    assert '"X-Request-Id"' in client

    # The legacy /uploads/kie route is now ROXY-owned durable storage, so trend
    # previews do not depend on expiring provider URLs.
    assert "Persist a reusable reference under ROXY ownership" in uploads
    assert "ReferenceStaticStorage.persist_stream" in uploads


def test_inline_trend_admin_backend_enforces_real_admin_permission() -> None:
    trends = _read(ROOT / "app" / "api" / "v1" / "trends.py")

    assert 'AdminAccount.user_id == user_id' in trends
    assert 'AdminAccount.is_active.is_(True)' in trends
    assert 'AdminPolicy.authorize_action(account, "social.moderate", confirmed=True)' in trends
    assert '@router.get("/manage")' in trends
    assert '@router.post("/manage")' in trends
    assert '@router.patch("/manage/{trend_id}")' in trends
    assert '@router.delete("/manage/{trend_id}")' in trends
    assert '@router.post("/manage/{trend_id}/activate")' in trends
    assert "TrendService.validate_recipe" in trends
    assert "AdminCommandLedger.execute" in trends

    # Static /{trend_id} routes must be registered after /manage so FastAPI
    # cannot interpret the literal word 'manage' as a UUID trend id.
    assert trends.index('@router.get("/manage")') < trends.index('@router.get("/{trend_id}")')
