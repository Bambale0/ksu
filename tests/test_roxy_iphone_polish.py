from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_iphone_polish_is_loaded_last() -> None:
    brand = _read("roxy-brand.js")
    assert '/mini-app/roxy-approved-surfaces.css' in brand
    assert '/mini-app/roxy-iphone-polish.css' in brand
    assert '/mini-app/roxy-model-categories.js' in brand
    assert brand.index('/mini-app/roxy-iphone-polish.css') > brand.index('/mini-app/roxy-approved-surfaces.css')


def test_iphone_polish_keeps_existing_ui_but_fixes_mobile_density() -> None:
    css = _read("roxy-iphone-polish.css")
    for token in (
        "@media (max-width: 430px)",
        ".product-header",
        ".brand-mark",
        ".balance",
        ".roxy-approved-hero",
        ".roxy-earn-step",
        ".roxy-media-card",
        ".family-tabs",
        ".studio-bottom-nav",
        "env(safe-area-inset-bottom, 0px)",
        "min-height: 44px",
        "font-size: 9.5px !important",
    ):
        assert token in css


def test_model_categories_are_derived_from_backend_catalog() -> None:
    script = _read("roxy-model-categories.js")
    assert 'fetch("/api/v1/generations/models"' in script
    assert 'image: "Фото"' in script
    assert 'video: "Видео"' in script
    assert 'audio: "Музыка"' in script
    assert "state.models.filter" in script
    assert "model.media_type === state.activeMedia" in script
    assert 'document.getElementById("modelSelect")' in script
    assert 'document.getElementById("familyTabs")' in script
    assert "option.hidden = !visible" in script
    assert "option.disabled = !visible" in script


def test_no_hardcoded_model_ids_in_category_layer() -> None:
    script = _read("roxy-model-categories.js")
    # The layer categorizes whatever the backend exposes; it must not silently
    # maintain a second, stale model catalog in frontend code.
    for model_id in (
        "gpt-image-2-t2i",
        "nano-banana-2",
        "seedance-2.5",
        "kling-3.0",
        "veo-3.1",
        "gemini-omni-video",
    ):
        assert model_id not in script
