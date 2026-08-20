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
        "generations": ("app.js", "shell.js", "social.js", "roxy-music.js", "roxy-history-management.js"),
        "discovery": ("roxy-discovery.js",),
        "feed": ("feed.js", "roxy-discovery.js", "studio-workspace.js"),
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
        "batches": ("bulk.js", "roxy-batch-embedded.js"),
    }
    missing = [domain for domain, files in coverage.items() if not all((MINI / name).exists() for name in files)]
    assert not missing, f"Backend domains without frontend files: {missing}"

    endpoint_contracts = {
        "/api/v1/me/preferences": ("profile-tools.js",),
        "/api/v1/notifications": ("profile-tools.js",),
        "/api/v1/promocodes/redeem": ("promo-recovery.js",),
        "/api/v1/referrals/withdrawals": ("partner.js",),
        "/api/v1/creator-partnership": ("roxy-profile-cabinet.js",),
        "/api/v1/generations": ("app.js", "shell.js", "roxy-history-management.js"),
        "/api/v1/feed": ("feed.js", "studio-workspace.js"),
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


def test_concrete_user_backend_actions_are_exposed_in_the_mini_app() -> None:
    """Guard mutations and secondary actions, not only top-level endpoint prefixes."""
    contracts = {
        "profile-tools.js": (
            "/api/v1/me/preferences",
            "/api/v1/notifications?limit=50",
            "/api/v1/notifications/read-all",
            "/read`, { method: \"POST\"",
            "/api/v1/support/tickets",
            "/messages`,",
            "/${action}",
        ),
        "promo-recovery.js": ("/api/v1/promocodes/redeem",),
        "partner.js": (
            "/api/v1/referrals/stats",
            "/api/v1/referrals/invitations",
            "/api/v1/referrals/rewards",
            "/api/v1/referrals/withdrawals",
            "/cancel",
            "Присоединяйся к ROXY · AI Creative Studio",
        ),
        "roxy-profile-cabinet.js": (
            "/api/v1/creator-partnership",
            "/applications",
        ),
        "app.js": (
            "/api/v1/generations/models",
            "/api/v1/generations/quote",
            "/api/v1/generations",
            "/api/v1/uploads/kie",
            "/recreate",
        ),
        "roxy-history-management.js": (
            "/api/v1/generations?limit=50",
            "/history`, { method: \"DELETE\"",
            "/history/restore`, { method: \"POST\"",
        ),
        "feed.js": (
            "/api/v1/feed",
            "/like",
            "/share",
            "/comments",
            "/remix",
            "/link",
        ),
        "studio-workspace.js": (
            "/publish",
            "method: \"DELETE\"",
            "Убрать публикацию",
        ),
        "trends.js": (
            "/api/v1/trends",
            "/run",
        ),
        "prompt-tools.js": (
            "/api/v1/prompt-tools",
            "/image-analysis",
            "/prompt-builder",
        ),
        "studio-shell.js": (
            "/api/v1/references",
            "/api/v1/presets",
        ),
        "primary-card-checkout.js": (
            "/api/v1/payments/card/packages",
            "/api/v1/payments/card/checkout",
            "/reconcile",
        ),
        "wallet.js": (
            "/api/v1/payments/packages",
            "/api/v1/payments",
            "/api/v1/me/transactions",
        ),
        "social.js": (
            "/api/v1/social/generations/",
            "/like",
            "/api/v1/social/profiles",
            "/subscribe",
            "/api/v1/social/subscriptions",
        ),
        "bulk.js": (
            "/api/v1/batch-generations/quote",
            "/api/v1/batch-generations/",
            "/retry-quote",
            "/retry",
            "/history`, { method: \"DELETE\"",
            "Убрать из истории",
        ),
        "onboarding.js": (
            "/api/v1/onboarding",
            "/complete",
        ),
    }
    missing: list[str] = []
    for filename, tokens in contracts.items():
        source = _read(filename)
        for token in tokens:
            if token not in source:
                missing.append(f"{filename}: {token}")
    assert not missing, "Backend actions without frontend hooks:\n" + "\n".join(missing)


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
    assert "fetch(" not in source
    assert "MutationObserver" not in source


def test_parity_features_are_mounted_before_the_canonical_design_system() -> None:
    brand = _read("roxy-brand.js")
    assert '/mini-app/roxy-parity-navigation.css' in brand
    assert '/mini-app/roxy-parity-navigation.js' in brand
    assert '/mini-app/roxy-history-management.css' in brand
    assert '/mini-app/roxy-history-management.js' in brand
    assert '/mini-app/roxy-design-system.css?v=1' in brand
    assert '/mini-app/roxy-fhd-density.css' not in brand
    assert '/mini-app/roxy-mobile-runtime.css' not in brand
    assert brand.index('/mini-app/roxy-profile-cabinet.js') < brand.index('/mini-app/roxy-parity-navigation.js')
    assert brand.index('/mini-app/roxy-parity-navigation.js') < brand.index('/mini-app/roxy-design-system.css?v=1')


def test_wide_and_mobile_density_are_owned_by_one_design_system() -> None:
    css = _read("roxy-design-system.css")
    for token in (
        "--roxy-content: 840px",
        "@media (min-width: 720px)",
        "@media (max-width: 430px)",
        "grid-template-columns: minmax(0, 1.03fr) minmax(300px, .97fr)",
        "grid-template-columns: repeat(5",
        "--tg-content-safe-area-inset-bottom",
        "min-height: 44px",
        "object-fit: cover",
        "object-fit: contain",
    ):
        assert token in css


def test_telegram_safe_area_and_viewport_logic_stay_in_runtime_not_visual_overrides() -> None:
    css = _read("roxy-design-system.css")
    runtime = _read("roxy-mobile-runtime.js")
    assert "--tg-content-safe-area-inset-bottom" in css
    assert "env(safe-area-inset-bottom" not in css
    assert "tg?.safeAreaInset" in runtime
    assert "tg?.contentSafeAreaInset" in runtime
    assert "tg?.viewportStableHeight" in runtime
    assert "window.visualViewport" in runtime
