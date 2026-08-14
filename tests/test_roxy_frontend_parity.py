from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def _combined(*names: str) -> str:
    return "\n".join(_read(name) for name in names)


def test_user_backend_domains_have_frontend_consumers() -> None:
    """Every user-facing backend domain must have a real Mini App consumer.

    Privileged /admin-* routers intentionally belong to /admin-app and are not
    duplicated into the customer Mini App.
    """
    coverage = {
        "me": ("account-overview.js", "profile-tools.js", "wallet.js"),
        "onboarding": ("onboarding.js",),
        "promocodes": ("promo-recovery.js",),
        "referrals": ("partner.js", "roxy-economy.js"),
        "creator-partnership": ("roxy-profile-cabinet.js",),
        "generations": ("app.js", "shell.js", "social.js", "roxy-music.js"),
        "discovery": ("roxy-discovery.js",),
        "feed": ("feed.js", "roxy-discovery.js"),
        "trends": ("trends.js", "roxy-discovery.js"),
        "prompt-tools": ("prompt-tools.js", "roxy-create-center.js"),
        "references": ("studio-shell.js", "studio-workspace.js"),
        "presets": ("studio-shell.js", "studio-workspace.js"),
        "media": ("shell.js", "app.js"),
        "payments": ("wallet.js", "primary-card-checkout.js", "payment-surface.js"),
        "notifications": ("profile-tools.js",),
        "social": ("social.js",),
        "support": ("profile-tools.js",),
        "uploads": ("app.js",),
        "batches": ("bulk.js",),
    }
    missing = [domain for domain, files in coverage.items() if not all((MINI / name).exists() for name in files)]
    assert not missing, f"Backend domains without frontend files: {missing}"

    endpoint_contracts = {
        "/api/v1/me/preferences": ("profile-tools.js",),
        "/api/v1/notifications": ("profile-tools.js",),
        "/api/v1/promocodes/redeem": ("promo-recovery.js",),
        "/api/v1/referrals/withdrawals": ("partner.js",),
        "/api/v1/creator-partnership": ("roxy-profile-cabinet.js",),
        "/api/v1/generations": ("app.js", "shell.js"),
        "/api/v1/feed": ("feed.js",),
        "/api/v1/trends": ("trends.js", "roxy-discovery.js"),
        "/api/v1/prompt-tools": ("prompt-tools.js", "roxy-create-center.js"),
        "/api/v1/references": ("studio-shell.js", "studio-workspace.js"),
        "/api/v1/presets": ("studio-shell.js", "studio-workspace.js"),
        "/api/v1/payments": ("wallet.js", "payment-surface.js"),
        "/api/v1/social": ("social.js",),
        "/api/v1/support/tickets": ("profile-tools.js",),
        "/api/v1/batch-generations": ("bulk.js",),
    }
    uncovered = []
    for endpoint, files in endpoint_contracts.items():
        source = _combined(*files)
        if endpoint not in source:
            uncovered.append(endpoint)
    assert not uncovered, f"User endpoints without a frontend call: {uncovered}"


def test_frontend_parity_navigation_surfaces_existing_tools_without_duplicate_api_clients() -> None:
    source = _read("roxy-parity-navigation.js")
    for token in (
        "Уведомления",
        "Промокод",
        "Поддержка",
        "Подписки",
        "Референсы",
        "Пресеты",
        "Тренды",
        "Prompt Tools",
        "Batch",
        "Рефералы",
        "Creator",
        "Настройки",
        'window.KsuStudioShell?.openLibrary',
        '#profileNotificationList',
        '#supportComposeForm',
        '.promo-section',
        '.social-profile-section',
    ):
        assert token in source
    # This layer is navigation-only: it must not duplicate backend fetch logic.
    assert "fetch(" not in source
    assert "MutationObserver" not in source


def test_parity_and_fhd_layers_are_mounted_before_mobile_acceptance_overrides() -> None:
    brand = _read("roxy-brand.js")
    assert '/mini-app/roxy-parity-navigation.css' in brand
    assert '/mini-app/roxy-parity-navigation.js' in brand
    assert '/mini-app/roxy-fhd-density.css' in brand
    assert brand.index('/mini-app/roxy-profile-cabinet.js') < brand.index('/mini-app/roxy-parity-navigation.js')
    assert brand.index('/mini-app/roxy-fhd-density.css') < brand.index('/mini-app/roxy-mobile-runtime.css')


def test_full_hd_density_uses_wide_canvas_without_giant_media() -> None:
    css = _read("roxy-fhd-density.css")
    for token in (
        "--roxy-fhd-max: 1760px",
        "@media (min-width: 1440px)",
        "@media (min-width: 1800px)",
        "grid-template-columns: repeat(6",
        "grid-template-columns: repeat(7",
        "--roxy-media-thumb-h: 150px",
        "max-height: var(--roxy-media-thumb-h)",
        "max-height: var(--roxy-media-detail-h)",
        "object-fit: cover",
        "object-fit: contain",
    ):
        assert token in css


def test_mobile_media_stays_compact_and_responsive() -> None:
    css = _read("roxy-fhd-density.css")
    assert "@media (max-width: 720px)" in css
    assert "--roxy-media-thumb-h: 132px" in css
    assert "grid-template-columns: repeat(2" in css
    assert "@media (max-width: 380px)" in css
    assert "--roxy-media-thumb-h: 116px" in css


def test_fhd_layer_does_not_replace_telegram_safe_area_runtime() -> None:
    density = _read("roxy-fhd-density.css")
    mobile = _read("roxy-mobile-runtime.css")
    assert "1920px" not in density  # responsive master canvas, not a fixed viewport lock
    assert "--roxy-content-safe-bottom" in mobile
    assert "env(safe-area-inset-bottom, 0px)" in mobile
