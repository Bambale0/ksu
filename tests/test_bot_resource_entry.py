from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendPhoto

from app.bot.handlers import launcher
from app.core.config import settings
from app.services.feed import FeedNotFoundError, FeedService
from app.services.partner import PartnerService
from app.services.trends import TrendService

RESOURCE = uuid.UUID("11111111-2222-4333-8444-555555555555")


def message(payload: str) -> SimpleNamespace:
    return SimpleNamespace(
        text=f"/start {payload}",
        from_user=SimpleNamespace(id=999),
        answer=AsyncMock(),
        answer_photo=AsyncMock(),
        answer_video=AsyncMock(),
        answer_audio=AsyncMock(),
    )


@pytest.fixture
def start_dependencies(monkeypatch):
    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")
    create = AsyncMock(return_value=SimpleNamespace(id=uuid.UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")))
    monkeypatch.setattr(launcher.UserService, "get_or_create", create)
    generic = AsyncMock()
    monkeypatch.setattr(launcher, "_send_launcher", generic)
    return create, generic


def test_public_referral_opens_bot_not_app(monkeypatch):
    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")
    assert PartnerService.referral_link(777) == "https://t.me/RoxyExampleBot?start=ref_777"
    assert FeedService.post_deep_link(RESOURCE, "777") == (
        "https://t.me/RoxyExampleBot?start=feed_11111111-2222-4333-8444-555555555555_ref_777"
    )


@pytest.mark.parametrize("media_type,method", [("image", "answer_photo"), ("video", "answer_video"), ("audio", "answer_audio")])
async def test_start_trend_previews_exact_resource_before_app(monkeypatch, start_dependencies, media_type, method):
    create, generic = start_dependencies
    get_public = AsyncMock(return_value={
        "id": str(RESOURCE), "title": "Портрет <public>", "description": "Описание тренда",
        "media_type": media_type, "preview_url": "https://media.example/public",
    })
    monkeypatch.setattr(TrendService, "get_public", get_public)
    msg = message("trend_11111111-2222-4333-8444-555555555555_ref_777")
    await launcher.start_app_only(msg, AsyncMock(), AsyncMock())
    create.assert_awaited_once()
    assert create.call_args.kwargs["inviter_telegram_id"] == 777
    generic.assert_not_awaited()
    sent = getattr(msg, method)
    sent.assert_awaited_once()
    kwargs = sent.call_args.kwargs
    assert "Портрет <public>" in kwargs["caption"]
    assert kwargs["parse_mode"] is None
    query = parse_qs(urlparse(kwargs["reply_markup"].inline_keyboard[0][0].web_app.url).query)
    assert query["start_payload"] == ["trend_11111111-2222-4333-8444-555555555555_ref_777"]
    assert query["startapp"] == query["start_payload"]


async def test_start_feed_uses_public_card_and_keeps_sharer(monkeypatch, start_dependencies):
    create, generic = start_dependencies
    monkeypatch.setattr(FeedService, "assert_surface_visible", AsyncMock(return_value=object()))
    card = AsyncMock(return_value={
        "id": str(RESOURCE), "result_url": "https://media.example/post.mp4",
        "media": [{"content_type": "video/mp4"}], "model": "ROXY",
        "author": {"display_name": "Author", "telegram_id": 123},
        "prompt": "PRIVATE PROMPT MUST NOT BE RENDERED",
    })
    monkeypatch.setattr(FeedService, "get_feed_generation_card", card)
    msg = message("feed_11111111-2222-4333-8444-555555555555_ref_777")
    await launcher.start_app_only(msg, AsyncMock(), AsyncMock())
    assert create.call_args.kwargs["inviter_telegram_id"] == 777
    card.assert_awaited_once()
    assert card.call_args.kwargs["generation_id"] == RESOURCE
    generic.assert_not_awaited()
    msg.answer_video.assert_awaited_once()
    kwargs = msg.answer_video.call_args.kwargs
    assert "PRIVATE PROMPT" not in kwargs["caption"]
    query = parse_qs(urlparse(kwargs["reply_markup"].inline_keyboard[0][0].web_app.url).query)
    assert query["start_payload"] == ["feed_11111111-2222-4333-8444-555555555555_ref_777"]


async def test_unpublished_feed_never_renders_private_media(monkeypatch, start_dependencies):
    create, generic = start_dependencies
    monkeypatch.setattr(FeedService, "assert_surface_visible", AsyncMock(side_effect=FeedNotFoundError("not public")))
    for name in ("get_feed_generation_card", "get_profile_generation_card"):
        monkeypatch.setattr(FeedService, name, AsyncMock(side_effect=FeedNotFoundError("not public")))
    msg = message("feed_11111111-2222-4333-8444-555555555555_ref_777")
    await launcher.start_app_only(msg, AsyncMock(), AsyncMock())
    assert create.call_args.kwargs["inviter_telegram_id"] is None
    msg.answer_photo.assert_not_awaited()
    msg.answer_video.assert_not_awaited()
    msg.answer.assert_awaited_once()
    assert "недоступ" in msg.answer.call_args.args[0].lower()
    generic.assert_not_awaited()


async def test_unavailable_trend_has_no_resource_button(monkeypatch, start_dependencies):
    monkeypatch.setattr(TrendService, "get_public", AsyncMock(side_effect=LookupError("missing")))
    msg = message("trend_11111111-2222-4333-8444-555555555555_ref_777")
    await launcher.start_app_only(msg, AsyncMock(), AsyncMock())
    msg.answer_photo.assert_not_awaited()
    assert "недоступ" in msg.answer.call_args.args[0].lower()
    button = msg.answer.call_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert "11111111" not in button.web_app.url


async def test_media_bad_request_falls_back_to_resource_text(monkeypatch, start_dependencies):
    monkeypatch.setattr(TrendService, "get_public", AsyncMock(return_value={
        "id": str(RESOURCE), "title": "Тренд", "media_type": "image",
        "preview_url": "https://media.example/expired.jpg",
    }))
    msg = message("trend_11111111-2222-4333-8444-555555555555_ref_777")
    msg.answer_photo.side_effect = TelegramBadRequest(method=SendPhoto(chat_id=999, photo="x"), message="wrong file identifier")
    await launcher.start_app_only(msg, AsyncMock(), AsyncMock())
    msg.answer.assert_awaited_once()
    assert "Тренд" in msg.answer.call_args.args[0]
    assert "trend_11111111" in msg.answer.call_args.kwargs["reply_markup"].inline_keyboard[0][0].web_app.url


async def test_blurred_post_does_not_expose_unblurred_media(monkeypatch, start_dependencies):
    monkeypatch.setattr(FeedService, "assert_surface_visible", AsyncMock(return_value=object()))
    monkeypatch.setattr(FeedService, "get_feed_generation_card", AsyncMock(return_value={
        "id": str(RESOURCE), "result_url": "https://media.example/post.jpg",
        "feed_blurred": True, "author": {"display_name": "Author"},
    }))
    msg = message("feed_11111111-2222-4333-8444-555555555555_ref_777")
    await launcher.start_app_only(msg, AsyncMock(), AsyncMock())
    msg.answer_photo.assert_not_awaited()
    msg.answer.assert_awaited_once()


async def test_plain_ref_keeps_generic_launcher_and_payload(start_dependencies):
    create, generic = start_dependencies
    msg = message("ref_777")
    await launcher.start_app_only(msg, AsyncMock(), AsyncMock())
    assert create.call_args.kwargs["inviter_telegram_id"] == 777
    assert generic.call_args.kwargs["payload"] == "ref_777"


@pytest.mark.parametrize("error_kind", ["forbidden", "network", "chat_not_found"])
async def test_delivery_failures_do_not_trigger_duplicate_text_send(monkeypatch, start_dependencies, error_kind):
    from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError

    monkeypatch.setattr(TrendService, "get_public", AsyncMock(return_value={
        "id": str(RESOURCE), "title": "Тренд", "media_type": "image",
        "preview_url": "https://media.example/preview.jpg",
    }))
    msg = message("trend_11111111-2222-4333-8444-555555555555_ref_777")
    method = SendPhoto(chat_id=999, photo="x")
    failures = {
        "forbidden": TelegramForbiddenError(method=method, message="bot was blocked"),
        "network": TelegramNetworkError(method=method, message="timeout"),
        "chat_not_found": TelegramBadRequest(method=method, message="chat not found"),
    }
    failure = failures[error_kind]
    msg.answer_photo.side_effect = failure
    with pytest.raises(type(failure)):
        await launcher.start_app_only(msg, AsyncMock(), AsyncMock())
    msg.answer_photo.assert_awaited_once()
    msg.answer.assert_not_awaited()


async def test_missing_preview_still_opens_exact_trend(monkeypatch, start_dependencies):
    monkeypatch.setattr(TrendService, "get_public", AsyncMock(return_value={
        "id": str(RESOURCE), "title": "Тренд без превью", "preview_url": None,
    }))
    msg = message("trend_11111111-2222-4333-8444-555555555555")
    await launcher.start_app_only(msg, AsyncMock(), AsyncMock())
    msg.answer_photo.assert_not_awaited()
    msg.answer.assert_awaited_once()
    assert "Тренд без превью" in msg.answer.call_args.args[0]
    button = msg.answer.call_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert parse_qs(urlparse(button.web_app.url).query)["start_payload"] == [
        "trend_11111111-2222-4333-8444-555555555555"
    ]


async def test_profile_only_shared_post_resolves_specific_card(monkeypatch, start_dependencies):
    create, generic = start_dependencies
    monkeypatch.setattr(FeedService, "assert_surface_visible", AsyncMock(
        side_effect=[FeedNotFoundError("not in feed"), object()]
    ))
    feed_card = AsyncMock(side_effect=FeedNotFoundError("not in feed"))
    profile_card = AsyncMock(return_value={
        "id": str(RESOURCE), "result_url": "https://media.example/profile.jpg",
        "author": {"display_name": "Profile author"},
    })
    monkeypatch.setattr(FeedService, "get_feed_generation_card", feed_card)
    monkeypatch.setattr(FeedService, "get_profile_generation_card", profile_card)
    msg = message("feed_11111111-2222-4333-8444-555555555555_ref_777")
    await launcher.start_app_only(msg, AsyncMock(), AsyncMock())
    assert create.call_args.kwargs["inviter_telegram_id"] == 777
    profile_card.assert_awaited_once()
    msg.answer_photo.assert_awaited_once()
    generic.assert_not_awaited()


async def test_repeated_start_keeps_payload_and_one_preview_per_request(monkeypatch, start_dependencies):
    create, generic = start_dependencies
    monkeypatch.setattr(TrendService, "get_public", AsyncMock(return_value={
        "id": str(RESOURCE), "title": "Тренд", "media_type": "image",
        "preview_url": "https://media.example/preview.jpg",
    }))
    msg = message("trend_11111111-2222-4333-8444-555555555555_ref_777")
    session, state = AsyncMock(), AsyncMock()
    for _ in range(2):
        await launcher.start_app_only(msg, session, state)
    assert create.await_count == 2
    assert msg.answer_photo.await_count == 2
    assert session.commit.await_count == 2
    for call in create.call_args_list:
        assert call.kwargs["inviter_telegram_id"] == 777
    for call in msg.answer_photo.call_args_list:
        button = call.kwargs["reply_markup"].inline_keyboard[0][0]
        assert parse_qs(urlparse(button.web_app.url).query)["start_payload"] == [
            "trend_11111111-2222-4333-8444-555555555555_ref_777"
        ]
    generic.assert_not_awaited()


async def test_existing_user_never_receives_duplicate_referral_or_welcome(monkeypatch):
    from app.services.referral_antifraud import ReferralAntifraudService
    from app.services.users import UserService
    from app.services.wallet import WalletService

    user = SimpleNamespace(id=uuid.uuid4())
    telegram_user = SimpleNamespace(
        id=999, username="viewer", first_name="Viewer", last_name=None, language_code="ru",
    )
    session = AsyncMock()
    session.scalar.return_value = user
    credit, attach = AsyncMock(), AsyncMock()
    monkeypatch.setattr(WalletService, "credit", credit)
    monkeypatch.setattr(ReferralAntifraudService, "attach_new_user", attach)
    for inviter in (777, 777, 888):
        assert await UserService.get_or_create(
            session, telegram_user, inviter_telegram_id=inviter,
        ) is user
    credit.assert_not_awaited()
    attach.assert_not_awaited()
    session.execute.assert_not_awaited()


def test_installed_link_contract_cannot_restore_startapp(monkeypatch):
    from app.services import mini_app_link_contract
    from app.services.feed_links import mini_app_deep_link

    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")
    monkeypatch.setattr(mini_app_link_contract, "_INSTALLED", False)
    # Restore class descriptors after testing the legacy installer.
    monkeypatch.setattr(FeedService, "post_deep_link", FeedService.__dict__["post_deep_link"])
    monkeypatch.setattr(FeedService, "profile_deep_link", FeedService.__dict__["profile_deep_link"])
    monkeypatch.setattr(FeedService, "remix_deep_link", FeedService.__dict__["remix_deep_link"])
    monkeypatch.setattr(PartnerService, "referral_link", PartnerService.__dict__["referral_link"])
    mini_app_link_contract.install_mini_app_link_contract()
    assert PartnerService.referral_link(777) == "https://t.me/RoxyExampleBot?start=ref_777"
    assert FeedService.post_deep_link(RESOURCE, "777") == (
        "https://t.me/RoxyExampleBot?start=feed_11111111-2222-4333-8444-555555555555_ref_777"
    )
    assert mini_app_deep_link("ref_777") == "https://t.me/RoxyExampleBot?startapp=ref_777"
