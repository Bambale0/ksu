from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_main_mini_app_uses_roxy_brand_from_first_paint() -> None:
    html = _read("index.html")
    assert "<title>ROXY · AI Creative Studio</title>" in html
    assert 'content="#0B0B10"' in html
    assert '/mini-app/roxy-brand.css' in html
    assert '/mini-app/roxy-brand.js' in html
    assert "ROXY · AI CREATIVE STUDIO" in html
    assert "Привет! Это ROXY ✨" in html
    assert "Твори. Генерируй. Зарабатывай." in html
    assert "Внутренние кредиты ROXY" in html
    assert "Ксю" not in html
    assert "КСЮ" not in html


def test_all_standalone_studio_surfaces_share_roxy_brand_layer() -> None:
    for name in ("trends.html", "prompt-tools.html", "batch.html"):
        html = _read(name)
        assert "ROXY" in html
        assert '/mini-app/roxy-brand.css' in html
        assert '/mini-app/roxy-brand.js' in html
        assert 'content="#0B0B10"' in html
        assert "Ксю" not in html
        assert "КСЮ" not in html


def test_roxy_palette_matches_reference_direction() -> None:
    css = _read("roxy-brand.css")
    for token in (
        "--roxy-bg: #09080f",
        "--roxy-surface: #18171f",
        "--roxy-violet: #8f6bff",
        "--roxy-purple: #b86cff",
        "--roxy-pink: #ff73ca",
        "--roxy-gradient:",
        "radial-gradient",
        "roxy-create-cta",
        "studio-bottom-nav",
        "studio-sidebar",
    ):
        assert token in css


def test_roxy_brand_runtime_keeps_telegram_chrome_and_dashboard_aligned() -> None:
    script = _read("roxy-brand.js")
    for token in (
        'setHeaderColor?.("#0B0B10")',
        'setBackgroundColor?.("#0B0B10")',
        'setBottomBarColor?.("#0B0B10")',
        "ROXY · AI CREATIVE STUDIO",
        'document.getElementById("roxyHomeBalance")?.remove()',
        'document.getElementById("roxyCreateCta")?.remove()',
        "hero.hidden = true",
        "arrangeHomeDashboard",
        "home.prepend(promo)",
        "/mini-app/roxy-generation-flow-v3.js?v=2",
        "/mini-app/roxy-generation-focus.css?v=2",
        "/mini-app/roxy-home-density-v3.css",
        "/mini-app/roxy-icons.js",
        "/mini-app/roxy-mature-ui.css",
        "/mini-app/roxy-approved-surfaces.css",
        "/mini-app/roxy-client-feedback.css",
    ):
        assert token in script
    assert script.index('/mini-app/roxy-client-feedback.css') > script.index('/mini-app/roxy-approved-surfaces.css')
    assert "MutationObserver" not in script
    assert "createTreeWalker" not in script
    assert "paymentRateLabel" not in script
    assert "roxBalanceText" not in script
    assert "roxRateText" not in script
    assert "initDataUnsafe" not in script


def test_roxy_visual_rebrand_does_not_hardcode_reference_economics() -> None:
    combined = "\n".join(
        _read(name)
        for name in (
            "index.html",
            "roxy-brand.js",
            "roxy-brand.css",
            "roxy-theme-compat.css",
            "trends.html",
            "prompt-tools.html",
            "batch.html",
        )
    )
    assert "1 ROX = 1" not in combined
    assert "1 ROX = 10" not in combined
    assert "ROX =" not in combined


def test_shell_integration_mounts_brand_after_product_layers() -> None:
    bridge = _read("shell-integration.js")
    assert "function mountRoxyBrand()" in bridge
    assert '/mini-app/roxy-brand.css' in bridge
    assert '/mini-app/roxy-theme-compat.css' in bridge
    assert '/mini-app/roxy-brand.js' in bridge
    assert 'let stylesheet = document.querySelector' in bridge
    assert "document.head.appendChild(stylesheet);" in bridge
    assert "document.head.appendChild(compatibility);" in bridge
    assert bridge.index("mountStudioWorkspace();") < bridge.index("mountRoxyBrand();")
    assert bridge.index("mountFunctionalRuntime();") < bridge.index("mountRoxyBrand();")
    assert 'script.src = "/mini-app/roxy-functional-runtime.js";' in bridge
    assert "script.async = false;" in bridge


def test_roxy_theme_wins_over_payment_surface_light_dark_tokens() -> None:
    css = _read("roxy-theme-compat.css")
    assert "html.roxy-brand-ready[data-ksu-theme]" in css
    assert "--bg: var(--roxy-bg)" in css
    assert "--button: var(--roxy-purple)" in css
    assert "color-scheme: dark" in css
    assert ".payment-method-choice.is-selected" in css
    assert ".payment-status-actions .primary" in css


def test_telegram_bot_default_onboarding_uses_roxy_name() -> None:
    config = (ROOT / "app" / "core" / "config.py").read_text(encoding="utf-8")
    start = (ROOT / "app" / "bot" / "handlers" / "start.py").read_text(encoding="utf-8")
    feed_api = (ROOT / "app" / "api" / "v1" / "feed.py").read_text(encoding="utf-8")
    assert 'onboarding_title: str = "Добро пожаловать в ROXY"' in config
    assert 'or "Добро пожаловать в ROXY"' in start
    assert 'or "Пользователь ROXY"' in feed_api
    assert "Добро пожаловать в Ксю" not in config
    assert "Добро пожаловать в Ксю" not in start
    assert "Пользователь Ксю" not in feed_api
