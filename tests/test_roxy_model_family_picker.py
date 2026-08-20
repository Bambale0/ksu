from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_family_picker_is_mounted_after_generation_flow() -> None:
    brand = _read("roxy-brand.js")

    flow_js = '/mini-app/roxy-generation-flow-v3.js?v=2'
    picker_css = '/mini-app/roxy-model-family-picker.css?v=1'
    picker_js = '/mini-app/roxy-model-family-picker.js?v=1'

    assert flow_js in brand
    assert picker_css in brand
    assert picker_js in brand
    assert brand.index(picker_js) > brand.index(flow_js)


def test_picker_collapses_duplicate_family_cards_into_versions() -> None:
    source = _read("roxy-model-family-picker.js")

    for token in (
        'const STORAGE_PREFIX = "roxy-model-family-choice-v1:"',
        'card.querySelector(".roxy-flow-model-title small")',
        "function versionLabel(family, title)",
        'return "Base"',
        "function groupCards(cards)",
        "group.length > 1 ? familyCard(group, mediaType) : cloneSingleton(group[0])",
        'picker.setAttribute("role", "radiogroup")',
        'chip.setAttribute("role", "radio")',
        'localStorage.setItem(storageKey(mediaType, family), item.productId)',
        'selected.card.click()',
        'grid.classList.add("roxy-family-picker-original")',
        '`${familyCount} ${familiesWord} · ${versionCount} ${versionsWord}`',
    ):
        assert token in source


def test_picker_keeps_version_choice_and_updates_selected_card_details() -> None:
    source = _read("roxy-model-family-picker.js")

    for token in (
        "function rememberedItem(items, mediaType, family)",
        'let selected = rememberedItem(items, mediaType, family)',
        'small.textContent = `Выбрано: ${selected.title}`',
        'footerCopy.textContent = "Открыть выбранную версию"',
        'card.dataset.selectedProductId = selected.productId',
        'chip.classList.toggle("is-active", active)',
        'chip.setAttribute("aria-checked", active ? "true" : "false")',
    ):
        assert token in source


def test_picker_observes_only_create_center_direct_replacements() -> None:
    source = _read("roxy-model-family-picker.js")

    assert 'const CENTER_ID = "roxyCreateCenterView"' in source
    assert 'centerObserver.observe(center, { childList: true })' in source
    assert "subtree: true" not in source
    assert 'window.addEventListener("roxy:shell-route-changed", attachCenterObserver)' in source
    assert 'window.addEventListener("roxy:route-changed", attachCenterObserver)' in source


def test_version_chips_are_mobile_accessible() -> None:
    css = _read("roxy-model-family-picker.css")

    for token in (
        ".roxy-family-picker-original",
        ".roxy-flow-family-open:focus-visible",
        ".roxy-flow-version-chip:focus-visible",
        ".roxy-flow-version-picker.is-scrollable",
        "min-height: 44px",
        "@media (max-width: 430px)",
        "@media (prefers-reduced-motion: reduce)",
    ):
        assert token in css
