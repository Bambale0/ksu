from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest

from app.api.deps import _validated_startapp_inviter
from app.api.v1.trends import share_trend
from app.core.config import settings
from app.db.admin_models import AdminTrend
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
async def test_trend_startapp_inviter_is_the_sharer_not_the_trend_author() -> None:
    trend_id = uuid.uuid4()
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(id=trend_id, is_active=True)),
    )

    inviter = await _validated_startapp_inviter(
        session,  # type: ignore[arg-type]
        trend_payload(trend_id, 777),
    )

    assert inviter == 777
    session.get.assert_awaited_once_with(AdminTrend, trend_id)


@pytest.mark.asyncio
async def test_inactive_or_legacy_trend_does_not_create_referral_attribution() -> None:
    trend_id = uuid.uuid4()
    inactive_session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(id=trend_id, is_active=False)),
    )

    assert await _validated_startapp_inviter(
        inactive_session,  # type: ignore[arg-type]
        trend_payload(trend_id, 777),
    ) is None
    assert await _validated_startapp_inviter(
        inactive_session,  # type: ignore[arg-type]
        trend_payload(trend_id),
    ) is None
