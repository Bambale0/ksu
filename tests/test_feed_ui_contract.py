from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_feed_api_has_distinct_discovery_and_profile_contracts() -> None:
    source = _read("app/api/v1/feed.py")
    assert '@router.get("/feed")' in source
    assert '@router.get("/feed/{generation_id}")' in source
    assert '@router.get("/profiles/{referral_code}/feed")' in source
    assert '@router.post("/feed/{generation_id}/publish")' in source
    assert '@router.post("/feed/{generation_id}/like")' in source
    assert '@router.post("/feed/{generation_id}/share")' in source
    assert '@router.get("/feed/{generation_id}/comments")' in source
    assert '@router.post("/feed/{generation_id}/comments"' in source
    assert '@router.post("/feed/{generation_id}/remix"' in source
    assert 'surface: Literal["feed", "profile"]' in source


def test_mini_app_feed_uses_backend_visibility_contract() -> None:
    source = _read("app/web/mini_app/feed.js")
    integration = _read("app/web/mini_app/shell-integration.js")
    for token in (
        "/api/v1/feed?sort=",
        "/api/v1/profiles/",
        "/feed/${encodeURIComponent(item.id)}/like",
        "/feed/${encodeURIComponent(item.id)}/share",
        "/feed/${encodeURIComponent(item.id)}/comments",
        "/feed/${encodeURIComponent(item.id)}/remix",
        "/feed/${encodeURIComponent(generationId)}/publish",
        "JSON.stringify({ surface })",
    ):
        assert token in source
    assert 'script.src = "/mini-app/feed.js"' in integration
    assert 'stylesheet.href = "/mini-app/feed.css"' in integration
    assert "innerHTML" not in source
    assert "document.write" not in source
    assert "eval(" not in source
    assert "new Function(" not in source


def test_legacy_bot_feed_domain_is_kept_but_customer_navigation_is_app_only() -> None:
    source = _read("app/bot/handlers/feed.py")
    dispatcher = _read("app/bot/dispatcher.py")
    keyboard = _read("app/bot/keyboards.py")
    assert "edit_media" in source
    assert "InputMediaPhoto" in source
    assert "InputMediaVideo" in source
    assert 'surface="feed"' in source
    assert 'surface="profile"' in source
    assert "profile_visible_only=True" in source
    assert "FeedService.remix(" in source
    assert "FeedService.get_profile_generation_card" in source
    assert "FeedService.get_feed_generation_card" in source

    # The legacy handler remains available as migration/reference code, but the
    # production Telegram dispatcher must not expose a second customer UI.
    assert "dispatcher.include_router(launcher.router)" in dispatcher
    assert "dispatcher.include_router(feed.router)" not in dispatcher

    main_menu = keyboard.split("def main_menu()", 1)[1]
    assert 'return app_launcher_menu(route="home")' in main_menu
    assert 'route="catalog"' not in main_menu
    assert 'fallback_callback="feed:open"' not in main_menu


def test_start_flow_preserves_feed_deep_link_through_onboarding() -> None:
    source = _read("app/bot/handlers/start.py")
    assert "pending_start_payload" in source
    assert "parse_feed_deep_link" in source
    assert "handle_deep_link" in source
    assert 'link.action != "ref"' in source


def test_remix_deep_link_executes_action_not_preview_only() -> None:
    source = _read("app/bot/handlers/feed.py")
    block = source.split('if link.action == "remix":', 1)[1]
    assert "FeedService.remix(" in block
    assert "source_generation_id=link.generation_id" in block
    assert "source.prompt" not in block
