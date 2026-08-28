from __future__ import annotations

import random
from decimal import Decimal
from pathlib import Path

import pytest

from app.api.v1.feed import _direct_mini_app_link
from app.core.config import settings
from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.services.feed import FeedService
from app.services.feed_links import bot_start_link, mini_app_deep_link, post_payload
from app.services.feed_static import FeedStaticStorage


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "frontend" / "mini-app"


def _telegram_id() -> int:
    return random.randint(8_000_000_000_000, 8_899_999_999_999)


@pytest.mark.asyncio
async def test_other_user_can_repeat_public_work_without_seeing_hidden_prompt() -> None:
    filename = f"repeat-hidden-{random.randint(100_000, 999_999)}.png"
    target = FeedStaticStorage.ensure_root() / filename
    target.write_bytes(b"\x89PNG\r\n\x1a\nroxy-repeat-contract")
    local_url = f"{FeedStaticStorage.public_prefix()}/{filename}"

    try:
        async with SessionFactory() as session:
            author = User(telegram_id=_telegram_id(), first_name="Author")
            viewer = User(telegram_id=_telegram_id(), first_name="Viewer")
            session.add_all([author, viewer])
            await session.flush()

            source = Generation(
                user_id=author.id,
                kind="text_to_image",
                status="succeeded",
                prompt="private server-side prompt",
                result_url=local_url,
                cost_rox=Decimal("8.00"),
                provider="kie",
                parameters={
                    "_model_id": "nano-banana-2",
                    "_result_urls": [local_url],
                    "_feed_static": True,
                },
                publication_scope="feed",
                is_public_feed=True,
                is_profile_visible=True,
                feed_prompt_visible=False,
                feed_references_visible=False,
            )
            session.add(source)
            await session.commit()

            card = await FeedService.get_feed_generation_card(
                session,
                generation_id=source.id,
                viewer_user_id=viewer.id,
            )

            assert card["is_mine"] is False
            assert card["prompt"] == ""
            assert card["prompt_hidden"] is True
            assert card["prompt_actions_allowed"] is True
            assert card["repeat_allowed"] is True
    finally:
        target.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_trend_publication_does_not_advertise_unsupported_repeat() -> None:
    filename = f"repeat-trend-{random.randint(100_000, 999_999)}.png"
    target = FeedStaticStorage.ensure_root() / filename
    target.write_bytes(b"\x89PNG\r\n\x1a\nroxy-repeat-trend-contract")
    local_url = f"{FeedStaticStorage.public_prefix()}/{filename}"

    try:
        async with SessionFactory() as session:
            author = User(telegram_id=_telegram_id(), first_name="Trend Author")
            viewer = User(telegram_id=_telegram_id(), first_name="Viewer")
            session.add_all([author, viewer])
            await session.flush()

            source = Generation(
                user_id=author.id,
                kind="text_to_image",
                status="succeeded",
                prompt="server trend prompt",
                result_url=local_url,
                cost_rox=Decimal("8.00"),
                provider="kie",
                parameters={
                    "_model_id": "nano-banana-2",
                    "_result_urls": [local_url],
                    "_feed_static": True,
                },
                action_type="trend",
                publication_scope="feed",
                is_public_feed=True,
                is_profile_visible=True,
                feed_prompt_visible=False,
                feed_references_visible=False,
            )
            session.add(source)
            await session.commit()

            card = await FeedService.get_feed_generation_card(
                session,
                generation_id=source.id,
                viewer_user_id=viewer.id,
            )

            assert card["prompt_actions_allowed"] is False
            assert card["repeat_allowed"] is False
    finally:
        target.unlink(missing_ok=True)


def test_public_post_link_uses_main_mini_app_even_without_short_name(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "")
    payload = post_payload("7c585918-e99a-42a9-a616-0dbbfc6f7c02", 123456)
    legacy = bot_start_link(payload)
    direct = (
        "https://t.me/RoxyExampleBot?startapp="
        "feed_7c585918-e99a-42a9-a616-0dbbfc6f7c02_ref_123456"
    )

    assert legacy == (
        "https://t.me/RoxyExampleBot?start="
        "feed_7c585918-e99a-42a9-a616-0dbbfc6f7c02_ref_123456"
    )
    assert mini_app_deep_link(payload) == direct
    assert _direct_mini_app_link(legacy) == direct


def test_feed_surfaces_expose_repeat_and_resilient_share_actions() -> None:
    tiktok = (MINI / "components" / "tiktok-feed-surface.tsx").read_text(encoding="utf-8")
    deep_link = (MINI / "components" / "feed-startapp-app.tsx").read_text(encoding="utf-8")
    post_publish = (MINI / "components" / "post-publish-share-prompt.tsx").read_text(encoding="utf-8")

    assert 'aria-label="Повторить"' in tiktok
    assert "card.prompt_actions_allowed !== false" in tiktok
    assert "api.remix(card.id" in tiktok

    assert "copyToClipboard" in deep_link
    assert "navigator.clipboard.writeText" not in deep_link

    assert "openTelegramShare" in post_publish
    assert "https://t.me/share/url" in post_publish
    assert "navigator.clipboard" not in post_publish
