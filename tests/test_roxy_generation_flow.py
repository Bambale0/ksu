from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_generation_flow_is_mounted_after_create_center() -> None:
    brand = _read("roxy-brand.js")

    create_js = '/mini-app/roxy-create-center.js'
    flow_css = '/mini-app/roxy-generation-flow.css?v=1'
    flow_js = '/mini-app/roxy-generation-flow.js?v=1'

    assert create_js in brand
    assert flow_css in brand
    assert flow_js in brand
    assert brand.index(flow_js) > brand.index(create_js)


def test_photo_and_video_have_separate_model_first_flows() -> None:
    source = _read("roxy-generation-flow.js")

    for token in (
        '["text", "Текст → фото"]',
        '["edit", "Редактирование"]',
        '["reference", "Референсы"]',
        '["text", "Текст → видео"]',
        '["image", "Фото → видео"]',
        '["video", "Видео → видео"]',
        '["motion", "Motion"]',
        'model.media_type === mediaType',
        'model?.ui_schema?.scenario?.items',
        'localStorage.setItem("ksu-selected-model", model.id)',
        'sessionStorage.setItem(RETURN_KEY, model.media_type',
    ):
        assert token in source

    assert "Фото и видео — отдельные генерационные контуры" in source
    assert "Формат" in source
    assert "Модель" in source
    assert "Режим" in source
    assert "Параметры" in source
    assert "Цена" in source
    assert "Запуск" in source


def test_video_flow_enters_builder_directly_without_home_bounce() -> None:
    source = _read("roxy-generation-flow.js")

    assert 'window.KsuStudioShell.open("create")' in source
    assert 'window.KsuStudioShell.open("home")' not in source
    assert 'document.getElementById("builderView")' in source
    assert 'document.getElementById("modelSelect")' in source
    assert 'select.dispatchEvent(new Event("change", { bubbles: true }))' in source
    assert '#builderHomeButton' in source
    assert "returnFromBuilder(mediaType)" in source


def test_generation_flow_keeps_existing_schema_builder_server_authoritative() -> None:
    source = _read("roxy-generation-flow.js")
    app = _read("app.js")

    assert 'api("/api/v1/generations/models")' in source
    assert "/api/v1/generations/quote" not in source
    assert 'api("/api/v1/generations",' not in source

    assert 'apiFetch("/api/v1/generations/quote"' in app
    assert 'apiFetch("/api/v1/generations"' in app
    assert "renderDynamicForm()" in app
    assert "validationErrors()" in app
    assert "/api/v1/uploads/kie" in app


def test_generation_flow_styles_are_responsive_and_accessible() -> None:
    css = _read("roxy-generation-flow.css")

    for token in (
        ".roxy-flow-model-grid",
        ".roxy-flow-lanes",
        ".roxy-flow-model-card:focus-visible",
        "@media (max-width: 760px)",
        "@media (max-width: 430px)",
        "@media (prefers-reduced-motion: reduce)",
        "linear-gradient(110deg, #9B5CFF 0%, #FF5FB7 100%)",
    ):
        assert token in css
