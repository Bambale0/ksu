from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.deps import _audit_signed_referral_once
from app.services.feed_links import FeedDeepLink
from app.services.referral_audit import log_referral_admission


class _FakeRedis:
    def __init__(self) -> None:
        self.calls = 0

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool | None:
        assert key.startswith("referral-audit:startapp:")
        assert value == "1"
        assert ex == 60
        assert nx is True
        self.calls += 1
        return True if self.calls == 1 else None


@pytest.mark.asyncio
async def test_signed_referral_audit_is_deduplicated_and_never_logs_raw_init_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    redis = _FakeRedis()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))
    link = FeedDeepLink(action="ref", referral_telegram_id=339795159)

    with caplog.at_level(logging.INFO, logger="ksu.referrals"):
        await _audit_signed_referral_once(
            request,
            visitor_telegram_id=123456789,
            link=link,
            accepted=True,
        )
        await _audit_signed_referral_once(
            request,
            visitor_telegram_id=123456789,
            link=link,
            accepted=True,
        )

    records = [record for record in caplog.records if record.name == "ksu.referrals"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "visitor_telegram_id=123456789" in message
    assert "inviter_telegram_id=339795159" in message
    assert "action=ref" in message
    assert "accepted=True" in message
    assert "query_id=" not in message
    assert "hash=" not in message
    assert "user=" not in message
    assert redis.calls == 2


def test_referral_admission_audit_exposes_outcome_without_credentials(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="ksu.referrals"):
        log_referral_admission(
            visitor_telegram_id=777,
            inviter_telegram_id=339795159,
            attached=True,
            reason="attached",
        )

    record = next(record for record in caplog.records if record.name == "ksu.referrals")
    assert record.referral_event == "admission"
    assert record.referral_attached is True
    assert record.referral_reason == "attached"
    assert record.visitor_telegram_id == 777
    assert record.inviter_telegram_id == 339795159
    assert "init_data" not in record.__dict__
    assert "telegram_init_data" not in record.__dict__


def test_referral_audit_code_has_no_raw_telegram_transport_dependency() -> None:
    audit = Path("app/services/referral_audit.py").read_text(encoding="utf-8")
    deps = Path("app/api/deps.py").read_text(encoding="utf-8")
    record_block = Path("app/services/referral_antifraud.py").read_text(encoding="utf-8").split(
        "async def _record", 1
    )[1].split("async def _count_since", 1)[0]

    assert "x_telegram_init_data" not in audit
    assert "signed_start_param" not in audit
    assert "log_signed_referral_validation" in deps
    assert "referral-audit:startapp:" in deps
    assert "log_referral_admission" in record_block
