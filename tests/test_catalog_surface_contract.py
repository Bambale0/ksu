from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "mini-app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_catalog_replaces_studio_in_customer_bottom_navigation() -> None:
    css = _read(FRONTEND / "app" / "ux-polish.css")
    e2e = _read(FRONTEND / "e2e" / "roxy-user-scenarios.spec.mjs")
    launcher = _read(ROOT / "app" / "bot" / "handlers" / "launcher.py")
    keyboard = _read(ROOT / "app" / "bot" / "keyboards.py")

    assert ".bottom-nav button:first-child" in css
    assert "display: none" in css
    assert "['Лента', 'Каталог', 'Создать', 'Партнёры', 'Профиль']" in e2e
    assert 'return "catalog"' in launcher
    assert 'return app_launcher_menu(route="catalog")' in keyboard


def test_catalog_exposes_bot_tools_and_admin_published_trends() -> None:
    catalog = _read(FRONTEND / "components" / "catalog-capabilities.tsx")
    social = _read(FRONTEND / "components" / "roxy-social-app.tsx")
    api = _read(FRONTEND / "lib" / "api.ts")

    for token in (
        "Фото-модели",
        "Видео-модели",
        "Музыка",
        "Описание по фото",
        "Описание по видео",
        "Сценарий для видео",
        "Пакетная обработка",
    ):
        assert token in catalog
    assert "api.promptTools()" in catalog
    assert 'href: "/mini-app/batch/"' in catalog
    assert "api.trends()" in social
    assert "trends: (mediaType?:" in api
    assert "`/api/v1/trends?limit=60" in api
    assert "api.models()" in social


def test_batch_screen_is_shared_react_shell_and_legacy_url_redirects() -> None:
    batch = _read(FRONTEND / "app" / "batch" / "page.tsx")
    legacy = _read(FRONTEND / "public" / "batch.html")

    for token in (
        "StandaloneShell",
        "api.models()",
        "api.upload(file)",
        "/api/v1/batch-generations/quote",
        "/api/v1/batch-generations",
        "/retry-quote",
        "/retry",
        "Idempotency-Key",
        "failed_count",
        "succeeded_count",
        "ui_schema",
    ):
        assert token in batch
    assert "2–20" in batch
    assert "Пакетная обработка" in batch
    assert "DynamicBatchField" in batch
    assert 'window.location.replace(\'/mini-app/batch/\')' in legacy
    assert 'href="/mini-app/batch/"' in legacy
