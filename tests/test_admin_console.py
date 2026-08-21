from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_WEB = ROOT / "app" / "web" / "admin_app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_web_admin_static_surface_is_removed() -> None:
    main = _read(ROOT / "app" / "main.py")
    dispatcher = _read(ROOT / "app" / "bot" / "dispatcher.py")
    retired = _read(ROOT / "app" / "bot" / "handlers" / "admin_web_removed.py")

    assert 'app.mount("/mini-app"' in main
    assert 'app.mount("/admin-app"' not in main
    assert "admin_app_dir" not in main
    assert not ADMIN_WEB.exists()

    assert "admin_web_removed.disable_web_admin_button(admin)" in dispatcher
    assert "dispatcher.include_router(admin_web_removed.router)" in dispatcher
    assert 'F.data == "admin:web"' in retired
    assert "Web-админка удалена" in retired


def test_telegram_admin_remains_operator_surface() -> None:
    bot = _read(ROOT / "app" / "bot" / "handlers" / "admin.py")
    dispatcher = _read(ROOT / "app" / "bot" / "dispatcher.py")

    assert 'Command("admin")' in bot
    assert 'AdminAccount.is_active.is_(True)' in bot
    assert "📊 Сводка" in bot
    assert "📣 Рассылка" in bot
    assert "🏷 Тарифы" in bot
    assert "dispatcher.include_router(admin.router)" in dispatcher
    assert "dispatcher.include_router(admin_extensions.router)" in dispatcher


def test_admin_api_contour_stays_mounted_after_web_removal() -> None:
    main = _read(ROOT / "app" / "main.py")
    router = _read(ROOT / "app" / "api" / "router.py")
    internal = _read(ROOT / "app" / "api" / "internal_admin.py")

    assert "app.include_router(internal_admin_router)" in main
    for module in (
        "admin_auth",
        "admin_users",
        "admin_operations",
        "admin_payments",
        "admin_accounts",
        "admin_audit",
        "admin_capabilities",
        "admin_control",
        "admin_creator_partnership",
    ):
        assert f"api_router.include_router({module}.router)" in router

    assert 'APIRouter(prefix="/internal/admin"' in internal
    assert 'Header(alias="Idempotency-Key")' in internal
    assert 'Header(alias="X-Admin-Confirm")' in internal
    assert 'Header(alias="X-Admin-Step-Up")' in internal


def test_sensitive_admin_writes_keep_policy_idempotency_and_step_up() -> None:
    internal = _read(ROOT / "app" / "api" / "internal_admin.py")
    users = _read(ROOT / "app" / "services" / "admin_users.py")
    policy = _read(ROOT / "app" / "services" / "admin_policy.py")

    for route in (
        "/users/{user_id}/block",
        "/users/{user_id}/unblock",
        "/users/{user_id}/balance-adjustments",
        "/payments/{payment_id}/reprocess",
        "/tariffs/publish",
        "/notifications/campaigns/{campaign_id}/start",
    ):
        assert route in internal

    assert "write.idempotency_key" in internal
    assert "confirmed=write.confirmed" in internal
    assert "step_up_valid=write.step_up_valid" in internal
    assert "AdminPolicy.require_permission" in users
    assert "AdminPolicyError" in policy


def test_session_revocation_uses_sessions_manage_not_security_read() -> None:
    source = _read(ROOT / "app" / "api" / "v1" / "admin_accounts.py")
    assert 'SessionsManageDep = Annotated[AdminContext, Depends(require_permission("sessions.manage"))]' in source
    signature = source.split('async def revoke_any_session(', 1)[1].split(') -> dict[str, bool]:', 1)[0]
    assert "context: SessionsManageDep" in signature
    assert "context: AdminSecurityReadDep" not in signature


def test_admin_contour_workflow_targets_backend_contracts_not_web_js() -> None:
    workflow = _read(ROOT / ".github" / "workflows" / "admin-console.yml")
    assert "name: Admin Contour" in workflow
    assert "pytest -q" in workflow
    assert "tests/test_admin_console.py" in workflow
    assert "node --check app/web/admin_app" not in workflow
