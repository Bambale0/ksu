from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_create_center_is_media_first_and_keeps_music_honest() -> None:
    source = _read("roxy-create-center.js")
    css = _read("roxy-create-center.css")
    for label in ("Фото", "Видео", "Музыка", "Что создаём?"):
        assert label in source
    assert 'type: "image"' in source
    assert 'type: "video"' in source
    assert 'type: "audio"' in source
    assert "disabled: true" in source
    assert "Скоро" in source
    assert 'model.media_type === mediaType' in source
    assert 'localStorage.setItem("ksu-selected-model", model.id)' in source
    assert ".roxy-media-grid" in css
    assert ".roxy-media-card.is-disabled" in css


def test_create_center_uses_existing_schema_driven_builder() -> None:
    source = _read("roxy-create-center.js")
    for token in (
        'api("/api/v1/generations/models")',
        'document.querySelectorAll(".shell-family-card")',
        'document.getElementById("modelSelect")',
        'select.dispatchEvent(new Event("change", { bubbles: true }))',
        'model?.ui_schema?.fields?.find((field) => field.name === "prompt")',
        'input.dispatchEvent(new Event("input", { bubbles: true }))',
    ):
        assert token in source
    assert "/api/v1/generations/quote" not in source
    assert "/api/v1/generations\"" not in source


def test_create_prompt_helper_is_embedded_and_server_authoritative() -> None:
    source = _read("roxy-create-center.js")
    for token in (
        "AI-помощник",
        "Промпт по фото",
        "Промпт для видео",
        'api("/api/v1/prompt-tools")',
        'api("/api/v1/prompt-tools/prompt-builder"',
        'purpose = model?.media_type === "video" ? "video" : "image"',
        'headers: { "Idempotency-Key": crypto.randomUUID() }',
        'api(`/api/v1/prompt-tools/${encodeURIComponent(taskId)}`)',
        "/api/v1/uploads/kie",
        "prompt_ru",
        "prompt_en",
    ):
        assert token in source
    assert "eval(" not in source
    assert "new Function" not in source
    assert "innerHTML" not in source


def test_navigation_and_brand_mount_create_center() -> None:
    navigation = _read("roxy-customer-navigation.js")
    brand = _read("roxy-brand.js")
    assert "RoxyCreateCenter?.open" in navigation
    assert 'classList.contains("roxy-create-center-open")' in navigation
    assert '/mini-app/roxy-create-center.css' in brand
    assert '/mini-app/roxy-create-center.js' in brand
