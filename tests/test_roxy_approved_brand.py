from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_approved_roxy_palette_is_loaded_last() -> None:
    brand = _read("roxy-brand.js")
    theme = _read("roxy-approved-theme.css")
    surfaces = _read("roxy-approved-surfaces.css")
    feedback = _read("roxy-client-feedback.css")

    assert '/mini-app/roxy-approved-theme.css' in brand
    assert '/mini-app/roxy-approved-home.js' in brand
    assert '/mini-app/roxy-approved-surfaces.css' in brand
    assert '/mini-app/roxy-client-feedback.css' in brand
    assert brand.index('/mini-app/roxy-approved-surfaces.css') > brand.index('/mini-app/roxy-approved-theme.css')
    assert brand.index('/mini-app/roxy-client-feedback.css') > brand.index('/mini-app/roxy-approved-surfaces.css')

    assert '.roxy-approved-hero' in theme
    assert '.roxy-earn-section' in theme
    for token in ("#0B0B10", "#9B5CFF", "#FF5FB7", "#FFFFFF", "#A6A6B3"):
        assert token in feedback
    assert "linear-gradient(110deg, #9B5CFF 0%, #FF5FB7 100%)" in feedback
    assert "#b768ff" not in feedback.lower()
    assert "#8f63ff" not in feedback.lower()
    assert "#ff69c9" not in feedback.lower()


def test_final_surface_layer_covers_every_customer_surface() -> None:
    surfaces = _read("roxy-approved-surfaces.css")
    expected_selectors = (
        ".roxy-reference-start-card.is-featured",  # Home
        ".roxy-catalog-quick-card",                # Catalog
        ".roxy-media-card",                        # Create center
        ".roxy-cabinet-action",                    # Profile
        ".roxy-history-management",                # History
        ".payment-package",                        # Wallet
        ".feed-card",                              # Community/deep Feed
        ".roxy-child-screen-back",                 # Child routes
        ".trend-card",                             # Standalone trends
        ".tool-panel",                             # Prompt tools
        ".batch-result",                           # Batch
        ".partner-stat",                           # Partner cabinet
        ".onboarding-card",                        # Onboarding
    )
    for selector in expected_selectors:
        assert selector in surfaces

    for legacy_gold in ("#f0c77d", "#f4c57a", "#f6cf8e"):
        assert legacy_gold not in surfaces.lower()


def test_reference_home_has_no_legacy_gold_palette() -> None:
    reference = _read("roxy-reference-home.css").lower()
    for legacy_gold in ("#f0c77d", "#f4c57a", "#f6cf8e", "rgba(244,197,122"):
        assert legacy_gold not in reference
    assert "#8f63ff" in reference
    assert "#ff69c9" in reference


def test_logo_asset_is_used_by_product_chrome() -> None:
    logo = _read("roxy-logo.svg")
    surfaces = _read("roxy-approved-surfaces.css")
    brand = _read("roxy-brand.js")

    assert 'url(\'/mini-app/roxy-logo.svg\')' in surfaces
    assert "#9B5CFF" in logo
    assert "#FF5FB7" in logo
    assert "#b768ff" not in logo.lower()
    assert 'setText(".brand-mark", "RX"' in brand
    assert 'setText(".studio-sidebar-mark", "RX"' in brand


def test_withdrawable_rox_uses_white_silver_indicator() -> None:
    feedback = _read("roxy-client-feedback.css")
    assert ".roxy-balance-card.withdrawable .roxy-balance-type::before" in feedback
    assert "background: #FFFFFF" in feedback
    assert "border: 1px solid #A6A6B3" in feedback


def test_approved_home_explains_creator_economy_and_rox() -> None:
    script = _read("roxy-approved-home.js")

    for copy in (
        "Создавай. Публикуй.",
        "Зарабатывай.",
        "Как заработать ROX",
        "Создай работу",
        "Опубликуй",
        "Получай ROX",
    ):
        assert copy in script

    assert 'button("✦ Создать"' in script
    assert 'button("Каталог"' in script
    assert '"create"' in script
    assert '"catalog"' in script
    assert '${numeric} ROX' in script


def test_rox_copy_is_normalized_for_dynamic_wallet_and_generation_ui() -> None:
    script = _read("roxy-approved-home.js")

    assert "normalizeCopyString" in script
    assert "normalizeVisibleCopy(document.body)" in script
    assert "кр\\." in script
    assert "кредит" in script
    assert '"/ ROX"' in script
    assert 'document.querySelector(".studio-sidebar-balance-value")' in script


def test_standalone_tools_mount_the_roxy_brand_runtime() -> None:
    for name in ("trends.html", "batch.html", "prompt-tools.html"):
        markup = _read(name)
        assert '/mini-app/roxy-brand.css' in markup
        assert '/mini-app/roxy-brand.js' in markup