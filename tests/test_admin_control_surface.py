from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_WEB = ROOT / "app" / "web" / "admin_app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_static_web_admin_surface_is_not_shipped_or_mounted() -> None:
    main = _read(ROOT / "app" / "main.py")
    workflow = _read(ROOT / ".github" / "workflows" / "admin-console.yml")

    assert not ADMIN_WEB.exists()
    assert 'app.mount("/admin-app"' not in main
    assert 'app.mount("/mini-app"' in main
    assert "node --check app/web/admin_app" not in workflow
    assert "name: Admin Contour" in workflow


def test_retired_telegram_web_callback_is_handled_without_opening_webapp() -> None:
    dispatcher = _read(ROOT / "app" / "bot" / "dispatcher.py")
    retired = _read(ROOT / "app" / "bot" / "handlers" / "admin_web_removed.py")

    assert "admin_web_removed.disable_web_admin_button(admin)" in dispatcher
    assert "dispatcher.include_router(admin_web_removed.router)" in dispatcher
    assert 'F.data == "admin:web"' in retired
    assert "Web-админка удалена" in retired
    assert "WebAppInfo" not in retired


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


def test_control_backend_exposes_shared_admin_domains() -> None:
    source = _read(ROOT / "app" / "api" / "v1" / "admin_control.py")
    for token in (
        "/admin/control/users",
        "/admin/control/payments",
        "/admin/control/operations",
        "/admin/control/tickets",
        "/admin/control/promocodes",
        "/admin/control/exports/",
    ):
        assert token in source, token


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
