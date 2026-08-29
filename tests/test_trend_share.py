from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest

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
async def test_share_trend_returns_native_telegram_share_payload(
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

    assert result["id"] == str(trend_id)
    assert result["link"] == f"https://t.me/RoxyExampleBot?startapp=trend_{trend_id}"
    assert result["copy_link"] == result["link"]
    assert "Плёночный портрет" in result["share_text"]

    share = urlparse(result["share_url"])
    query = parse_qs(share.query)
    assert (share.scheme, share.netloc, share.path) == ("https", "t.me", "/share/url")
    assert query["url"] == [result["link"]]
    assert query["text"] == [result["share_text"]]
    get_public.assert_awaited_once()
