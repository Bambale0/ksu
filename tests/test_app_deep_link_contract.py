from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app.api.deps import _validated_startapp_inviter
from app.bot.keyboards import app_launcher_menu, main_menu_with_start_payload
from app.core.config import settings


@pytest.mark.asyncio
async def test_plain_ref_startapp_preserves_inviter_without_bot_start() -> None:
    assert await _validated_startapp_inviter(object(), "ref_123456") == 123456  # type: ignore[arg-type]


def _single_web_app_url(markup) -> str:  # type: ignore[no-untyped-def]
    button = markup.inline_keyboard[0][0]
    assert button.web_app is not None
    return button.web_app.url


def test_referral_launcher_url_matches_banano_tanyapi_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")

    parsed = urlparse(_single_web_app_url(app_launcher_menu(start_payload="ref_123456")))
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "roxy.example"
    assert parsed.path == "/mini-app/"
    assert query["route"] == ["catalog"]
    assert query["start_payload"] == ["ref_123456"]
    assert query["startapp"] == ["ref_123456"]
    assert query["ref"] == ["123456"]


def test_main_menu_carries_referral_payload_into_web_app_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")

    query = parse_qs(urlparse(_single_web_app_url(main_menu_with_start_payload("ref_42"))).query)

    assert query["start_payload"] == ["ref_42"]
    assert query["startapp"] == ["ref_42"]
    assert query["ref"] == ["42"]


def test_mini_app_entry_routes_all_public_deep_link_kinds() -> None:
    root = Path(__file__).resolve().parents[1]
    entry = (root / "frontend/mini-app/components/app-entry-gate.tsx").read_text(encoding="utf-8")
    telegram = (root / "frontend/mini-app/lib/telegram.ts").read_text(encoding="utf-8")
    profile = (root / "frontend/mini-app/components/profile-startapp-app.tsx").read_text(encoding="utf-8")
    post = (root / "frontend/mini-app/components/feed-startapp-app.tsx").read_text(encoding="utf-8")
    social = (root / "frontend/mini-app/components/roxy-social-app.tsx").read_text(encoding="utf-8")
    types = (root / "frontend/mini-app/lib/types.ts").read_text(encoding="utf-8")
    trend_page = (root / "frontend/mini-app/app/trend/page.tsx").read_text(encoding="utf-8")
    api = (root / "frontend/mini-app/lib/api.ts").read_text(encoding="utf-8")

    # Telegram launch-param recovery remains centralized, but a current
    # ROXY-owned start_payload must outrank Telegram's sticky SDK start_param
    # when the already-open WebView navigates from one deep-link target to
    # another (for example feed work -> author profile -> another feed work).
    assert "getStartParamFallback" in entry
    assert "function explicitInternalPayload()" in entry
    assert 'params.get("start_payload")' in entry
    assert "const payload = explicitInternalPayload() || getStartParamFallback();" in entry
    assert "initDataUnsafe?.start_param" in telegram
    assert "tgWebAppStartParam" in telegram
    assert '"start_payload"' in telegram
    assert "__ROXY_INITIAL_LAUNCH__" in telegram

    assert "feed_" in entry
    assert "remix_" in entry
    assert "posts_" in entry
    assert "profile_" in entry
    assert "trend_" in entry
    trend_link_line = next(line for line in entry.splitlines() if line.startswith("const TREND_LINK"))
    assert "(?:_ref_" in trend_link_line
    assert ")?$/i" in trend_link_line
    assert "TrendStartApp" in entry
    assert "/mini-app/trend/?id=" in entry
    assert "ProfileStartApp" in entry
    assert 'intent={target.kind}' in entry
    explicit_launch = entry.split("function explicitLaunchCarries", 1)[1].split("function profileTarget", 1)[0]
    assert "window.location.search" in explicit_launch
    assert "window.location.hash" in explicit_launch
    # Telegram retains SDK/snapshot start params for the whole WebView session.
    # Reopening an already-consumed target therefore requires a fresh product URL,
    # not a persistent launch snapshot or tgWebAppStartParam value.
    assert "__ROXY_INITIAL_LAUNCH__" not in explicit_launch
    assert "tgWebAppStartParam" not in explicit_launch
    assert '"start_payload"' in explicit_launch
    assert '"startapp"' in explicit_launch
    assert "clearStoredLaunchPayload" in profile
    assert "clearStoredLaunchPayload" in post

    assert "api.profileFeed(referralCode, 0)" in profile
    assert "data-profile-startapp-posts" in profile
    assert "start_payload" in profile

    # A shared profile-only post must still open, and remix/share must use the
    # surface on which the publication was actually found.
    assert 'api.feedItem(generationId, "feed")' in post
    assert 'api.feedItem(generationId, "profile")' in post
    assert "api.remix(card.id, surface)" in post
    assert "api.share(card.id, surface)" in post

    assert "profile_link?: string" in types
    assert "stats?.profile_link" in social
    assert "Поделиться профилем" in social
    assert "Профиль автора" in social

    assert "export type TrendShare" in types
    assert "shareTrend:" in api
    assert "/share`" in api
    assert "Поделиться трендом" in trend_page
    assert "openTelegramShare(result.share_url)" in trend_page
