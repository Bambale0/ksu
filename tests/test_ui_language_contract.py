from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "mini-app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_language_switch_uses_partial_preferences_api() -> None:
    provider = _read(FRONTEND / "components" / "ui-language-provider.tsx")
    me_api = _read(ROOT / "app" / "api" / "v1" / "me.py")
    service = _read(ROOT / "app" / "services" / "profile_preferences.py")

    assert 'method: "PATCH"' in provider
    assert 'body: JSON.stringify({ ui_language: next })' in provider
    assert 'method: "PUT"' not in provider
    assert '@router.patch("/preferences")' in me_api
    assert "class PatchPreferenceRequest" in me_api
    assert "async def patch(" in service


def test_language_translation_protects_editable_and_user_generated_content() -> None:
    provider = _read(FRONTEND / "components" / "ui-language-provider.tsx")
    feed = _read(FRONTEND / "components" / "tiktok-feed-surface.tsx")
    language = _read(FRONTEND / "lib" / "ui-language.ts")

    # Textarea values are never translated, while placeholders are still eligible.
    assert 'const SKIP_TEXT_SELECTOR' in provider
    assert '"textarea"' in provider.split("const SKIP_TEXT_SELECTOR", 1)[1].split("].join", 1)[0]
    assert '"textarea"' not in provider.split("const SKIP_SUBTREE_SELECTOR", 1)[1].split("].join", 1)[0]
    assert 'const TRANSLATED_ATTRIBUTES = ["placeholder", "aria-label", "title", "alt"]' in provider

    # User data gets explicit no-i18n boundaries instead of relying on text heuristics.
    assert '<strong data-no-i18n>{authorName(card)}</strong>' in feed
    assert 'data-no-i18n>{card.prompt}</p>' in feed
    assert 'data-no-i18n>{comment.text}</p>' in feed
    assert 'data-no-i18n>{detailsCard.prompt}</p>' in feed
    assert 'data-no-i18n>{currentProfile?.display_name' in feed

    # Runtime UI translation is anchored. Never replace month fragments inside arbitrary text.
    assert 'replaceAll(ru, en)' not in language
    assert 'изображений выбрано' in language
    assert 'images selected' in language


def test_language_switch_is_available_on_root_and_standalone_shells() -> None:
    layout = _read(FRONTEND / "app" / "layout.tsx")
    standalone = _read(FRONTEND / "components" / "standalone-shell.tsx")
    settings = _read(FRONTEND / "app" / "settings" / "page.tsx")

    assert "<UiLanguageProvider>" in layout
    assert "<LanguageSwitcher />" in standalone
    assert 'method: "PATCH"' in settings
    assert "ui_language" not in settings.split("body: JSON.stringify({", 1)[1].split("}),", 1)[0]
