from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_generation_flow_is_mounted_after_create_center() -> None:
    brand = _read("roxy-brand.js")

    create_js = '/mini-app/roxy-create-center.js'
    flow_css = '/mini-app/roxy-generation-flow.css?v=2'
    flow_js = '/mini-app/roxy-generation-flow.js?v=2'
    focus_css = '/mini-app/roxy-generation-focus.css?v=1'
    mode_bridge = '/mini-app/roxy-generation-mode-bridge.js?v=1'

    assert create_js in brand
    assert flow_css in brand
    assert flow_js in brand
    assert focus_css in brand
    assert mode_bridge in brand
    assert brand.index(flow_js) > brand.index(create_js)
    assert brand.index(mode_bridge) > brand.index(flow_js)


def test_catalog_groups_same_product_modes_into_one_card() -> None:
    source = _read("roxy-generation-flow.js")

    for token in (
        'title: "Nano Banana", ids: ["nano-banana", "nano-banana-edit"]',
        'title: "Seedream 4.0", ids: ["seedream-4-t2i", "seedream-4-edit"]',
        'title: "Seedream 5 Pro", ids: ["seedream-5-pro-t2i", "seedream-5-pro-i2i"]',
        'title: "GPT Image 2", ids: ["gpt-image-2-t2i", "gpt-image-2-i2i"]',
        'title: "Wan 2.7 Video", ids: ["wan-2.7-t2v", "wan-2.7-i2v", "wan-2.7-video-edit"]',
        'title: "Grok Video", ids: ["grok-video-t2v", "grok-video-i2v"]',
        "function buildProducts(mediaType)",
        "Режим выберется автоматически",
        "Ее Text/Image/Video режимы больше не раскиданы по каталогу.",
    ):
        assert token in source

    assert "laneDefinitions" not in source
    assert "operationLane" not in source


def test_selected_model_is_forced_exactly_after_family_switch() -> None:
    source = _read("roxy-generation-flow.js")

    for token in (
        "function ensureFamilySelected(model)",
        'document.querySelectorAll(".family-tab")',
        "buttonNode.textContent",
        "tab.click()",
        "function selectExactModel(modelId, attempt = 0)",
        'select.value = modelId',
        'select.dispatchEvent(new Event("change", { bubbles: true }))',
        'localStorage.setItem("ksu-selected-model", modelId)',
    ):
        assert token in source


def test_input_media_switches_underlying_variant_automatically() -> None:
    source = _read("roxy-generation-flow.js")

    for token in (
        "function sourceVariant(product, kind)",
        'model.operation === "video_edit"',
        '"image_to_video"',
        '"image_edit"',
        '"image_to_image"',
        "function uploadSmartSource(file, kind)",
        'api("/api/v1/uploads/kie"',
        "moveDraftToVariant(target, uploaded, kind)",
        "selectExactModel(target.id, 0)",
        "Без файла ROXY использует текстовый режим",
        "Добавить фото",
        "Добавить видео",
    ):
        assert token in source


def test_mode_bridge_persists_variant_before_builder_resumes() -> None:
    bridge = _read("roxy-generation-mode-bridge.js")

    for token in (
        'const RESUME_KEY = "ksu-studio-open-builder"',
        'event.target.closest?.("#roxySmartSourcePanel input[type=\'file\']")',
        'event.stopImmediatePropagation()',
        'fetch("/api/v1/uploads/kie"',
        'writeDrafts(drafts)',
        'localStorage.setItem("ksu-selected-model", modelId)',
        'sessionStorage.setItem(RESUME_KEY, "1")',
        'window.location.reload()',
        'model.operation === "video_edit"',
        '"image_to_video"',
        '"image_edit"',
        '"image_to_image"',
    ):
        assert token in bridge


def test_builder_is_focused_on_only_selected_product() -> None:
    source = _read("roxy-generation-flow.js")
    css = _read("roxy-generation-focus.css")

    assert 'document.body?.classList.add("roxy-focused-model-flow")' in source
    assert 'id = "roxyFocusedModelHeader"' in source
    assert 'id = "roxySmartSourcePanel"' in source
    assert "#builderView .model-card > .family-tabs" in css
    assert "#builderView .model-card > #modelSelect" in css
    assert "#createHome > #roxyApprovedHero" in css
    assert "display: none !important" in css


def test_video_flow_enters_builder_without_returning_to_home() -> None:
    source = _read("roxy-generation-flow.js")

    assert 'window.KsuStudioShell.open("create")' in source
    assert 'window.KsuStudioShell.open("home")' not in source
    assert 'document.getElementById("builderView")' in source
    assert '#builderHomeButton' in source
    assert "returnFromBuilder(mediaType)" in source
    assert 'document.body?.classList.add("roxy-focused-model-pending")' in source


def test_generation_backend_remains_server_authoritative() -> None:
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
    focus = _read("roxy-generation-focus.css")

    for token in (
        ".roxy-flow-model-grid",
        ".roxy-flow-model-card:focus-visible",
        "@media (max-width: 760px)",
        "@media (max-width: 430px)",
        "@media (prefers-reduced-motion: reduce)",
        "linear-gradient(110deg, #9B5CFF 0%, #FF5FB7 100%)",
    ):
        assert token in css

    assert "@media (max-width: 720px)" in focus
    assert ".roxy-smart-source" in focus
