from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_reference_uploader_is_mounted_in_generation_runtime() -> None:
    brand = _read("roxy-brand.js")
    assert '/mini-app/roxy-reference-uploader.css?v=1' in brand
    assert '/mini-app/roxy-reference-uploader.js?v=1' in brand
    assert brand.index('/mini-app/roxy-generation-focus.css?v=2') < brand.index('/mini-app/roxy-reference-uploader.css?v=1')
    assert brand.index('/mini-app/roxy-reference-uploader.js?v=1') < brand.index('/mini-app/roxy-photo-controls.js?v=1')
    assert brand.index('/mini-app/roxy-reference-uploader.js?v=1') < brand.index('/mini-app/roxy-video-controls.js?v=1')


def test_reference_uploader_exposes_photo_and_video_reference_actions() -> None:
    script = _read("roxy-reference-uploader.js")
    for token in (
        '"nano-banana": "nano-banana-edit"',
        '"seedream-5-pro-t2i": "seedream-5-pro-i2i"',
        '"gpt-image-2-t2i": "gpt-image-2-i2i"',
        '"grok-image-t2i": "grok-image-i2i"',
        '"wan-2.7-t2v": "wan-2.7-i2v"',
        '"grok-video-t2v": "grok-video-i2v"',
        '"Фото-референсы"',
        '"Референсы для видео"',
        '"Добавить фото"',
        '"Первый кадр"',
        '"Последний кадр"',
        'input[type="file"]',
        'input.click()',
        'select.dispatchEvent(new Event("change", { bubbles: true }))',
        "copyCompatibleDraft",
    ):
        assert token in script

    # The new UX is only a discoverability/orchestration layer. The existing
    # app.js uploader remains the single implementation of provider uploads.
    assert 'fetch("/api/v1/uploads/kie"' not in script


def test_reference_uploader_keeps_native_reference_controls_visible() -> None:
    css = _read("roxy-reference-uploader.css")
    for token in (
        ".roxy-reference-upload-panel",
        ".roxy-reference-upload-button",
        "#dynamicForm .roxy-reference-native-group",
        "body.roxy-focused-model-flow #dynamicForm .roxy-native-source-hidden",
        "display: block !important",
        "border-style: dashed",
    ):
        assert token in css


def test_existing_uploader_still_owns_real_kie_upload_and_reference_drafts() -> None:
    app = _read("app.js")
    assert '/api/v1/uploads/kie' in app
    assert 'fileInput.type = "file"' in app
    assert 'fileInput.multiple = field.control === "files"' in app
    assert 'fileInput.accept = field.accept' in app
    assert 'fileInput.addEventListener("change", async () =>' in app
    assert 'await uploadLocalFile(field, file)' in app
    assert 'draft.values[field.name]' in app
