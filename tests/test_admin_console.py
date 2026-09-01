from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "app" / "web" / "admin_app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_admin_console_is_separate_static_app_and_bot_launcher_is_not_auth() -> None:
    main = _read(ROOT / "app" / "main.py")
    bot = _read(ROOT / "app" / "bot" / "handlers" / "admin.py")
    dispatcher = _read(ROOT / "app" / "bot" / "dispatcher.py")

    assert 'app.mount("/admin-app"' in main
    assert 'app.mount("/mini-app"' in main
    assert 'Command("admin")' in bot
    assert 'AdminAccount.is_active.is_(True)' in bot
    assert 'WebAppInfo(url=url)' in bot
    assert '"/admin-app/"' in bot or '/admin-app/' in bot
    assert "Веб-админка откроется с отдельной защищённой сессией." in bot
    assert "dispatcher.include_router(admin.router)" in dispatcher


def test_admin_console_never_persists_privileged_credentials_or_uses_html_injection() -> None:
    js = _read(ADMIN / "admin.js")
    assert "state.token" in js
    assert 'headers.Authorization = `Bearer ${state.token}`' in js
    assert '"X-Telegram-Init-Data"' in js
    assert "tg?.initData" in js
    assert "localStorage" not in js
    assert "sessionStorage" not in js
    assert "indexedDB" not in js
    assert "innerHTML" not in js
    assert "document.write" not in js
    assert "eval(" not in js
    assert "new Function(" not in js


def test_admin_console_covers_existing_operational_domains() -> None:
    js = _read(ADMIN / "admin.js")
    for token in (
        "/api/v1/admin/auth/login",
        "/api/v1/admin/auth/mfa/setup",
        "/api/v1/admin/auth/mfa/confirm",
        "/api/v1/admin/auth/step-up",
        "/api/v1/admin/auth/me",
        "/api/v1/admin/dashboard",
        "/api/v1/admin/users?",
        "/api/v1/admin/generations?",
        "/api/v1/admin/payments?",
        "/api/v1/admin/support/tickets?",
        "/api/v1/admin/withdrawals?",
        "/api/v1/admin/promocodes?",
        "/api/v1/admin/referrals/rewards?",
        "/api/v1/admin/security/overview",
        "/api/v1/admin/security/sessions?",
        "/api/v1/admin/audit?",
        "/api/v1/admin/admins",
        "/api/v1/admin/roles",
        "/api/v1/admin/auth/sessions",
    ):
        assert token in js, token

    assert "state.permissions = new Set(state.me.permissions || [])" in js
    assert "hasPermission(" in js


def test_sensitive_actions_require_separate_step_up_and_execute_click() -> None:
    html = _read(ADMIN / "index.html")
    js = _read(ADMIN / "admin.js")

    assert 'id="stepUpVerify"' in html
    assert 'id="stepUpExecute"' in html
    assert "Подтвердить код" in html
    assert "Выполнить действие" in html
    assert "state.pendingSensitive" in js
    assert "verifyStepUp" in js
    assert "executePendingSensitive" in js
    assert 'dom.stepUpExecute.hidden = false' in js
    assert 'dom.stepUpExecute.addEventListener("click", executePendingSensitive)' in js


def test_admin_self_sessions_match_backend_sessions_shape() -> None:
    js = _read(ADMIN / "admin.js")
    auth = _read(ROOT / "app" / "api" / "v1" / "admin_auth.py")
    marker = 'const data = await api("/api/v1/admin/auth/sessions")'
    assert marker in js
    after = js.split(marker, 1)[1]
    render_block = after.split("async function", 1)[0]
    assert "data.sessions || []" in render_block
    assert 'return {"sessions": [_session_view(row, context.session.id) for row in rows]}' in auth


def test_session_revocation_uses_sessions_manage_not_security_read() -> None:
    source = _read(ROOT / "app" / "api" / "v1" / "admin_accounts.py")
    assert 'SessionsManageDep = Annotated[AdminContext, Depends(require_permission("sessions.manage"))]' in source
    signature = source.split('async def revoke_any_session(', 1)[1].split(') -> dict[str, bool]:', 1)[0]
    assert "context: SessionsManageDep" in signature
    assert "context: AdminSecurityReadDep" not in signature


def test_admin_login_fits_short_telegram_webview_and_explains_launch_contract() -> None:
    html = _read(ADMIN / "index.html")
    css = _read(ADMIN / "admin.css")

    assert "100dvh" in css
    assert "overflow-y:auto" in css.replace(" ", "")
    assert "@media(max-height:700px)" in css.replace(" ", "")
    assert "кнопкой «Веб-админка»" in html
    assert "Прямой URL" in html
    assert html.index('id="loginButton"') < html.index('id="loginRecovery"')


def test_production_deploy_repairs_and_verifies_admin_security_key() -> None:
    workflow = _read(ROOT / ".github" / "workflows" / "deploy-production.yml")

    assert "ADMIN_SECURITY_KEY" in workflow
    assert "/dev/urandom" in workflow
    assert "settings.admin_security_key" in workflow
    assert 'curl -fsSI "${app_base}/admin-app/"' in workflow


def test_admin_console_files_are_present_and_node_checked() -> None:
    workflow = _read(ROOT / ".github" / "workflows" / "admin-console.yml")
    assert (ADMIN / "index.html").is_file()
    assert (ADMIN / "admin.css").is_file()
    assert (ADMIN / "admin.js").is_file()
    assert "node --check app/web/admin_app/admin.js" in workflow
