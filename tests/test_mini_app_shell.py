from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_shell_assets_are_loaded_in_stable_order() -> None:
    html = _read("index.html")
    app_pos = html.index('/mini-app/app.js')
    shell_pos = html.index('/mini-app/shell.js')
    bridge_pos = html.index('/mini-app/shell-integration.js')
    assert app_pos < shell_pos < bridge_pos


def test_shell_has_stable_top_level_navigation_and_views() -> None:
    html = _read("index.html")
    for view in ("create", "history", "wallet", "profile"):
        assert f'data-view="{view}"' in html
        assert f'data-shell-nav="{view}"' in html
    for element_id in (
        "createHome",
        "builderView",
        "generationDetailView",
        "historyMount",
        "walletBalance",
        "transactionList",
        "profileCard",
        "partnerPreview",
        "bottomNav",
    ):
        assert f'id="{element_id}"' in html


def test_shell_uses_signed_init_data_not_init_data_unsafe() -> None:
    shell = _read("shell.js")
    bridge = _read("shell-integration.js")
    assert "X-Telegram-Init-Data" in shell
    assert "tg.initData" in shell
    assert "initDataUnsafe" not in shell
    assert "initDataUnsafe" not in bridge


def test_shell_uses_current_telegram_navigation_and_safe_area_contract() -> None:
    shell = _read("shell.js")
    css = _read("styles.css")
    for token in (
        "BackButton",
        "viewportStableHeight",
        '"themeChanged"',
        '"viewportChanged"',
        '"safeAreaChanged"',
        '"contentSafeAreaChanged"',
    ):
        assert token in shell, token
    for token in (
        "--tg-content-safe-area-inset-top",
        "--tg-content-safe-area-inset-bottom",
        "--tg-content-safe-area-inset-left",
        "--tg-content-safe-area-inset-right",
        "--tg-viewport-stable-height",
        "env(safe-area-inset-bottom",
    ):
        assert token in css, token


def test_history_is_remounted_as_shell_content_and_legacy_button_hidden() -> None:
    css = _read("styles.css")
    shell = _read("shell.js")
    bridge = _read("shell-integration.js")
    assert "#ksuHistoryButton" in css
    assert ".history-mount .ksu-history-overlay" in css
    assert "ensureHistoryMounted" in shell
    assert "MutationObserver" in bridge
    assert "ksu-history-action" in bridge


def test_create_home_discovers_models_and_recent_server_state() -> None:
    shell = _read("shell.js")
    for endpoint in (
        "/api/v1/generations/models",
        "/api/v1/generations?limit=6",
        "/api/v1/me",
        "/api/v1/me/transactions",
        "/api/v1/referrals/stats",
    ):
        assert endpoint in shell, endpoint
    assert "ACTIVE_STATUSES" in shell
    assert "shellFamilyGrid" in _read("index.html")


def test_shell_docs_define_feature_boundaries() -> None:
    doc = (ROOT / "docs" / "MINI_APP_SHELL.md").read_text(encoding="utf-8")
    for token in (
        "Create",
        "History",
        "Wallet",
        "Profile",
        "BackButton",
        "contentSafeAreaChanged",
        "X-Telegram-Init-Data",
        "localStorage",
        "Wallet/Payments",
    ):
        assert token in doc, token


def test_ci_checks_every_mini_app_javascript_entrypoint() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    # CI must validate the whole Mini App directory so new JS entrypoints cannot
    # silently bypass syntax checks. Explicit per-file lists are intentionally avoided.
    for token in (
        "find app/web/mini_app",
        "-name '*.js'",
        "xargs -0 -n1 node --check",
    ):
        assert token in workflow
