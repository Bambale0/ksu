from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_concept_one_design_system_is_the_final_visual_authority() -> None:
    brand = _read("roxy-brand.js")
    design = _read("roxy-design-system.css")

    assert '/mini-app/roxy-approved-home.js' in brand
    assert '/mini-app/roxy-design-system.css?v=1' in brand
    assert brand.rindex('/mini-app/roxy-design-system.css?v=1') > brand.index('/mini-app/roxy-app-onboarding.css?v=1')

    for retired in (
        "roxy-approved-theme.css",
        "roxy-approved-surfaces.css",
        "roxy-client-feedback.css",
        "roxy-unified-controls.css",
        "roxy-iphone-polish.css",
        "roxy-fhd-density.css",
        "roxy-home-density-v3.css",
        "roxy-mature-ui.css",
        "roxy-mobile-runtime.css",
        "roxy-header-logo.css",
    ):
        assert f"/mini-app/{retired}" not in brand
        assert not (MINI / retired).exists()

    upper = design.upper()
    for token in ("#0B0B10", "#9B5CFF", "#FF5FB7", "#FFFFFF", "#A6A6B3"):
        assert token in upper


def test_concept_one_covers_the_eight_primary_customer_surfaces() -> None:
    design = _read("roxy-design-system.css")
    expected_selectors = (
        ".roxy-approved-hero",     # Home
        ".roxy-media-card",        # Create image/video/music launcher
        ".studio-result-pane",     # Result
        ".roxy-audio-player",      # Music result
        ".studio-library-grid",    # Library
        ".roxy-cabinet-action",    # Profile/settings
        ".dynamic-form",           # Generation settings from server schema
        ".roxy-history-list",      # History
        ".studio-bottom-nav",      # Primary mobile navigation
    )
    for selector in expected_selectors:
        assert selector in design

    for legacy_gold in ("#f0c77d", "#f4c57a", "#f6cf8e"):
        assert legacy_gold not in design.lower()


def test_current_logo_asset_is_used_by_product_chrome() -> None:
    logo = _read("roxy-logo.svg")
    brand = _read("roxy-brand.js")
    design = _read("roxy-design-system.css")

    assert "#9B5CFF" in logo
    assert "#FF5FB7" in logo
    assert 'const BRAND_LOGO_SRC = "/mini-app/assets/roxy-rx-logo-v5.webp?v=5"' in brand
    assert 'ensureBrandLogo(".brand-mark", headerBrand)' in brand
    assert 'ensureBrandLogo(".studio-sidebar-mark", sidebar)' in brand
    assert 'setText(".brand-mark", "RX"' not in brand
    assert ".roxy-brand-mark-logo" in design
    assert "object-fit: contain" in design


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


def test_standalone_tools_use_the_canonical_design_entrypoint() -> None:
    brand_entry = _read("roxy-brand.css")
    theme_compat = _read("roxy-theme-compat.css")
    assert '@import url("/mini-app/roxy-design-system.css?v=1")' in brand_entry
    assert '@import url("/mini-app/roxy-design-system.css?v=1")' in theme_compat

    for name in ("trends.html", "batch.html", "prompt-tools.html"):
        markup = _read(name)
        assert '/mini-app/roxy-brand.css' in markup
        assert '/mini-app/roxy-brand.js' in markup
