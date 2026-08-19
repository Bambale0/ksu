from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHOTO_JS = ROOT / "app" / "web" / "mini_app" / "roxy-photo-controls.js"
PHOTO_CSS = ROOT / "app" / "web" / "mini_app" / "roxy-photo-controls.css"
BRAND_JS = ROOT / "app" / "web" / "mini_app" / "roxy-brand.js"
KIE_PROVIDER = ROOT / "app" / "providers" / "kie.py"


def test_all_current_image_products_get_explicit_controls() -> None:
    source = PHOTO_JS.read_text(encoding="utf-8")
    for model_id in (
        "nano-banana",
        "nano-banana-pro",
        "nano-banana-2",
        "nano-banana-2-lite",
        "seedream-3-t2i",
        "seedream-4-t2i",
        "seedream-4.5-t2i",
        "seedream-5-lite-t2i",
        "seedream-5-pro-t2i",
        "gpt-image-1.5-t2i",
        "gpt-image-2-t2i",
        "wan-2.7-image",
        "wan-2.7-image-pro",
        "grok-image-t2i",
    ):
        assert f'"{model_id}"' in source

    assert '"Соотношение сторон"' in source
    assert '"Качество"' in source
    assert '"Сколько фото за раз"' in source
    assert 'options(["1K", "2K", "4K"])' in source


def test_photo_controls_use_fixed_selectors_instead_of_free_typing() -> None:
    source = PHOTO_JS.read_text(encoding="utf-8")
    styles = PHOTO_CSS.read_text(encoding="utf-8")

    assert 'document.createElement("select")' in source
    assert 'className = "roxy-photo-select"' in source
    assert 'className = "roxy-photo-segment"' in source
    assert 'setAttribute("aria-pressed"' in source
    assert ".roxy-photo-native-hidden" in styles
    assert ".roxy-photo-segment.is-active" in styles


def test_dynamic_provider_constraints_are_visible_in_the_ui_contract() -> None:
    source = PHOTO_JS.read_text(encoding="utf-8")

    assert 'const blocked = new Set(["5:4", "4:5", "3:1", "1:3", "9:21"])' in source
    assert 'modelId === "wan-2.7-image-pro" && hasSourceImages(modelId)' in source
    assert 'payload.parameters.resolution = "2K"' in source
    assert '"grok-image-t2i"' in source
    assert 'key: "enable_pro"' not in source  # config is built through the helper, not user text input
    assert 'segmented("enable_pro", "Качество"' in source


def test_extra_documented_fields_are_injected_into_quote_and_submit() -> None:
    source = PHOTO_JS.read_text(encoding="utf-8")

    assert 'url.pathname === "/api/v1/generations"' in source
    assert 'url.pathname === "/api/v1/generations/quote"' in source
    assert "applyExtraParameters(payload)" in source
    assert 'payload.parameters[control.key] = value' in source


def test_photo_layer_is_mounted_and_provider_submission_is_guarded() -> None:
    brand = BRAND_JS.read_text(encoding="utf-8")
    provider = KIE_PROVIDER.read_text(encoding="utf-8")

    assert 'roxy-photo-controls.css?v=1' in brand
    assert 'roxy-photo-controls.js?v=1' in brand
    assert "normalize_kie_image_input" in provider
    assert 'normalized_input = normalize_kie_image_input(model, input_data)' in provider
