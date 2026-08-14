from pathlib import Path

from app.api.v1.reference_presets import PresetWrite


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_studio_shell_is_loaded_by_existing_compatibility_bridge() -> None:
    bridge = _read("shell-integration.js")
    assert '/mini-app/studio-shell.css' in bridge
    assert '/mini-app/studio-shell.js' in bridge
    assert "mountStudioShell" in bridge


def test_studio_shell_exposes_five_primary_product_routes() -> None:
    script = _read("studio-shell.js")
    for route in ("home", "feed", "create", "history", "profile"):
        assert f'"{route}"' in script
    for label in ("Главная", "Лента", "Создать", "История", "Профиль"):
        assert label in script
    assert "studioBottomNav" in script
    assert "studioSidebar" in script


def test_studio_shell_keeps_models_schema_driven() -> None:
    script = _read("studio-shell.js")
    for model_family in (
        "nanobanana",
        "seedream",
        "gpt-image",
        "wan",
        "seedance",
        "kling",
        "grok",
    ):
        assert model_family not in script
    assert "ksu-selected-model" in script
    assert "ksu-generation-drafts-v1" in script


def test_studio_shell_integrates_existing_product_domains() -> None:
    script = _read("studio-shell.js")
    for endpoint in (
        "/api/v1/references?limit=100",
        "/api/v1/references",
        "/api/v1/presets",
    ):
        assert endpoint in script
    for page in ("trends.html", "batch.html", "prompt-tools.html"):
        assert page in script
    assert "feedOverlay" in script
    assert "resultCard" in script
    assert "studio-result-pane" in script


def test_studio_shell_uses_signed_telegram_auth_and_safe_area_css() -> None:
    script = _read("studio-shell.js")
    css = _read("studio-shell.css")
    assert "X-Telegram-Init-Data" in script
    assert "tg.initData" in script
    assert "initDataUnsafe" not in script
    for token in (
        "--tg-content-safe-area-inset-top",
        "--tg-content-safe-area-inset-bottom",
        "env(safe-area-inset-bottom",
        "prefers-reduced-motion",
    ):
        assert token in css


def test_video_preset_write_contract_keeps_billing_seconds() -> None:
    payload = PresetWrite(
        name="Video preset",
        model_id="model-under-test",
        prompt="hello",
        parameters={},
        reference_ids=[],
        billing_seconds=10,
    )
    assert payload.billing_seconds == 10
    assert payload.model_dump()["billing_seconds"] == 10
