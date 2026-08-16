from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_approved_roxy_palette_is_loaded_last() -> None:
    brand = _read("roxy-brand.js")
    theme = _read("roxy-approved-theme.css")

    assert '/mini-app/roxy-approved-theme.css' in brand
    assert '/mini-app/roxy-approved-home.js' in brand
    assert '#8f63ff' in theme
    assert '#ff69c9' in theme
    assert '--roxy-gradient' in theme
    assert '.roxy-approved-hero' in theme
    assert '.roxy-earn-section' in theme


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


def test_header_uses_rx_mark_instead_of_legacy_single_x() -> None:
    brand = _read("roxy-brand.js")
    assert 'setText(".brand-mark", "RX"' in brand
    assert 'setText(".studio-sidebar-mark", "RX"' in brand
