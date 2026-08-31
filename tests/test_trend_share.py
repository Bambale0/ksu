from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest

from app.api.deps import _validated_startapp_inviter
from app.api.v1.trends import share_trend
from app.core.config import settings
from app.services.feed_links import mini_app_deep_link, trend_payload
from app.services.trends import TrendService


def test_trend_payload_builds_direct_main_mini_app_link(monkeypatch: pytest.MonkeyPatch) -> None:
    trend_id = uuid.uuid4()
    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")

    payload = trend_payload(trend_id)
    link = mini_app_deep_link(payload)

    assert payload == f"trend_{trend_id}"
    assert link == f"https://t.me/RoxyExampleBot?startapp=trend_{trend_id}"


@pytest.mark.asyncio
async def test_share_trend_returns_native_telegram_share_payload_with_sharer_referral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trend_id = uuid.uuid4()
    trend = SimpleNamespace(id=trend_id, title="Плёночный портрет")
    get_public = AsyncMock(return_value=trend)
    monkeypatch.setattr(TrendService, "get_public", get_public)
    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")

    result = await share_trend(
        trend_id,
        SimpleNamespace(telegram_id=777),
        AsyncMock(),
    )

    expected_link = f"https://t.me/RoxyExampleBot?startapp=trend_{trend_id}_ref_777"
    assert result["id"] == str(trend_id)
    assert result["link"] == expected_link
    assert result["copy_link"] == expected_link
    assert "Плёночный портрет" in result["share_text"]

    share = urlparse(result["share_url"])
    query = parse_qs(share.query)
    assert (share.scheme, share.netloc, share.path) == ("https", "t.me", "/share/url")
    assert query["url"] == [result["link"]]
    assert query["text"] == [result["share_text"]]
    get_public.assert_awaited_once()


@pytest.mark.asyncio
async def test_share_trend_fallback_keeps_sharer_referral_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trend_id = uuid.uuid4()
    monkeypatch.setattr(
        TrendService,
        "get_public",
        AsyncMock(return_value={"id": str(trend_id), "title": "Кино-тренд"}),
    )
    monkeypatch.setattr(settings, "bot_username", "")
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")

    result = await share_trend(
        trend_id,
        SimpleNamespace(telegram_id=777),
        AsyncMock(),
    )

    parsed = urlparse(result["link"])
    query = parse_qs(parsed.query)
    expected_payload = trend_payload(trend_id, 777)
    assert (parsed.scheme, parsed.netloc, parsed.path) == (
        "https",
        "roxy.example",
        "/mini-app/trend/",
    )
    assert query["id"] == [str(trend_id)]
    assert query["start_payload"] == [expected_payload]
    assert query["startapp"] == [expected_payload]


@pytest.mark.asyncio
async def test_trend_startapp_inviter_is_the_sharer_not_the_trend_author(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trend_id = uuid.uuid4()
    session = object()
    get_public = AsyncMock(return_value={"id": str(trend_id), "title": "Public trend"})
    monkeypatch.setattr(TrendService, "get_public", get_public)

    inviter = await _validated_startapp_inviter(
        session,  # type: ignore[arg-type]
        trend_payload(trend_id, 777),
    )

    assert inviter == 777
    get_public.assert_awaited_once_with(session, trend_id=trend_id)


@pytest.mark.asyncio
async def test_non_public_or_legacy_trend_does_not_create_referral_attribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trend_id = uuid.uuid4()
    session = object()
    get_public = AsyncMock(side_effect=LookupError("Trend not found"))
    monkeypatch.setattr(TrendService, "get_public", get_public)

    assert await _validated_startapp_inviter(
        session,  # type: ignore[arg-type]
        trend_payload(trend_id, 777),
    ) is None
    assert await _validated_startapp_inviter(
        session,  # type: ignore[arg-type]
        trend_payload(trend_id),
    ) is None
    get_public.assert_awaited_once_with(session, trend_id=trend_id)
