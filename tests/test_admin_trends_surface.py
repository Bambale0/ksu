from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "app" / "web" / "admin_app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_admin_console_exposes_trend_manager() -> None:
    index = _read(ADMIN / "index.html")
    html = _read(ADMIN / "trends.html")
    workflow = _read(ROOT / ".github" / "workflows" / "admin-console.yml")

    assert 'href="/admin-app/trends.html"' in index
    assert 'id="trendForm"' in html
    assert 'id="trendModel"' in html
    assert 'id="trendPrompt"' in html
    assert 'id="trendPreviewUrl"' in html
    assert 'id="trendInputMode"' in html
    assert 'id="trendParameters"' in html
    assert 'id="trendList"' in html
    assert (ADMIN / "trends.css").is_file()
    assert (ADMIN / "trends.js").is_file()
    assert "node --check app/web/admin_app/trends.js" in workflow


def test_trend_manager_uses_admin_auth_and_server_owned_crud() -> None:
    js = _read(ADMIN / "trends.js")

    for token in (
        "/api/v1/admin/auth/login",
        "/api/v1/admin/auth/me",
        "/api/v1/admin/auth/logout",
        "/api/v1/admin/trends/options",
        'api("/api/v1/admin/trends")',
        'api("/api/v1/admin/trends", {',
        'method: "PATCH"',
        'method: "DELETE"',
        '/activate`, { method: "POST"',
        '"Idempotency-Key"',
        '"X-Admin-Confirm": "true"',
        '"X-Telegram-Init-Data"',
        "social.moderate",
    ):
        assert token in js, token

    assert "state.token" in js
    assert "localStorage" not in js
    assert "sessionStorage" not in js
    assert "indexedDB" not in js
    assert "innerHTML" not in js
    assert "document.write" not in js
    assert "eval(" not in js
    assert "new Function(" not in js


def test_admin_trend_backend_exposes_dynamic_model_options_and_editing() -> None:
    router = _read(ROOT / "app" / "api" / "router.py")
    manager = _read(ROOT / "app" / "api" / "v1" / "admin_trends.py")
    capabilities = _read(ROOT / "app" / "api" / "v1" / "admin_capabilities.py")

    assert "admin_trends," in router
    assert "api_router.include_router(admin_trends.router)" in router
    assert 'router = APIRouter(prefix="/admin/trends"' in manager
    assert 'require_permission("social.moderate")' in manager
    assert 'spec.public_dict() for spec in SPECS' in manager
    assert '@router.get("/options")' in manager
    assert '@router.patch("/{trend_id}")' in manager
    assert '@router.post("/{trend_id}/activate")' in manager
    assert "TrendService.validate_recipe" in manager
    assert "AdminCommandLedger.execute" in manager
    assert 'AdminPolicy.authorize_action(' in manager
    assert '"social.moderate"' in manager

    # Creation/deactivation already exist in the hardened admin-capabilities API;
    # the new manager UI must reuse them rather than creating an unguarded path.
    assert '@router.get("/trends")' in capabilities
    assert '@router.post("/trends", status_code=201)' in capabilities
    assert '@router.delete("/trends/{trend_id}")' in capabilities
