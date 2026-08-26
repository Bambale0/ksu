from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "app" / "web" / "admin_app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_admin_control_surface_is_present_and_discoverable() -> None:
    index = _read(ADMIN / "index.html")
    workflow = _read(ROOT / ".github" / "workflows" / "admin-console.yml")

    assert (ADMIN / "control.html").is_file()
    assert (ADMIN / "control.css").is_file()
    assert (ADMIN / "control.js").is_file()
    assert '/admin-app/control.html' in index
    assert "node --check app/web/admin_app/control.js" in workflow


def test_control_surface_keeps_privileged_credentials_memory_only_and_escapes_content() -> None:
    js = _read(ADMIN / "control.js")

    assert "state.token" in js
    assert 'Authorization", `Bearer ${state.token}`' in js
    assert "tg?.initData" in js
    for forbidden in (
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "innerHTML",
        "outerHTML",
        "document.write",
        "eval(",
        "new Function(",
    ):
        assert forbidden not in js
    assert "textContent" in js


def test_control_surface_uses_shared_backend_routes_and_command_headers() -> None:
    js = _read(ADMIN / "control.js")
    for token in (
        "/api/v1/admin/control/users",
        "/api/v1/admin/control/payments",
        "/api/v1/admin/control/operations",
        "/api/v1/admin/control/tickets",
        "/api/v1/admin/tariffs",
        "/api/v1/admin/cms/documents",
        "/api/v1/admin/notifications/campaigns",
        "/api/v1/admin/control/promocodes",
        "/api/v1/admin/prompts",
        "/api/v1/admin/trends",
        "/api/v1/admin/feed/",
        "/api/v1/admin/runtime",
        "/api/v1/admin/partners/analytics",
        "/api/v1/admin/control/exports/",
    ):
        assert token in js, token

    assert '"Idempotency-Key"' in js
    assert '"X-Admin-Confirm"' in js
    assert '"X-Request-Id"' in js
    assert "/api/v1/admin/auth/step-up" in js
    assert "/api/v1/admin/auth/me" in js
    assert "Доступ администратора не подтверждён" in js


def test_control_backend_is_thin_adapter_over_shared_services() -> None:
    source = _read(ROOT / "app" / "api" / "v1" / "admin_control.py")
    for service in (
        "AdminUserService",
        "AdminPaymentService",
        "AdminGenerationOperationService",
        "AdminSupportService",
        "AdminPromoService",
        "AdminExportService",
    ):
        assert service in source
    assert "WalletService." not in source
    assert "session.add(" not in source
    assert "session.execute(" not in source
    assert "Idempotency-Key" in source
    assert "X-Admin-Confirm" in source


def test_new_capability_backend_revalidates_permissions_server_side() -> None:
    source = _read(ROOT / "app" / "api" / "v1" / "admin_capabilities.py")
    deps = _read(ROOT / "app" / "api" / "admin_deps.py")

    assert "Depends(require_permission(" in source
    assert "AdminPolicy.has_permission(context.account, permission)" in deps
    for route in (
        '/admin/tariffs',
        '/admin/cms/documents',
        '/admin/notifications/campaigns',
        '/admin/prompts',
        '/admin/trends',
        '/admin/runtime',
        '/admin/partners/analytics',
    ):
        assert route.removeprefix('/admin') in source or route in source


def test_telegram_admin_extensions_recheck_admin_for_commands_and_callbacks() -> None:
    source = _read(ROOT / "app" / "bot" / "handlers" / "admin_extensions.py")
    dispatcher = _read(ROOT / "app" / "bot" / "dispatcher.py")

    assert "await _admin_account(session, message.from_user.id)" in source
    assert "await _admin_account(session, callback.from_user.id)" in source
    assert "await state.clear()" in source
    assert 'Command("admin_export")' in source
    assert 'Command("admin_promo")' in source
    assert 'Command("admin_withdrawal")' in source
    assert 'Command("admin_prompt")' in source
    assert 'Command("admin_generation")' in source
    assert "dispatcher.include_router(admin_extensions.router)" in dispatcher
