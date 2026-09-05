from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.core.config import settings
from app.providers.kie import KieClient, KieProviderError
from app.services.kie_credit_alerts import ALERT_STATE_KEY, KieCreditAlertService

ROOT = Path(__file__).resolve().parents[1]


class _CreditResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeKieHttpClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[str] = []

    async def get(self, path: str, **_kwargs: Any) -> _CreditResponse:
        self.calls.append(path)
        return _CreditResponse(self.payload)


class _FakeRedis:
    def __init__(self, value: str | None = None) -> None:
        self.value = value
        self.set_calls: list[tuple[str, str, int | None]] = []
        self.deleted: list[str] = []

    async def get(self, key: str) -> str | None:
        assert key == ALERT_STATE_KEY
        return self.value

    async def set(self, key: str, value: str, *, ex: int | None = None) -> None:
        assert key == ALERT_STATE_KEY
        self.value = value
        self.set_calls.append((key, value, ex))

    async def delete(self, key: str) -> None:
        assert key == ALERT_STATE_KEY
        self.value = None
        self.deleted.append(key)


class _FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


class _FakeCreditClient:
    def __init__(self, credits: Decimal) -> None:
        self.credits = credits

    async def get_remaining_credits(self) -> Any:
        return type("Balance", (), {"credits": self.credits})()


@pytest.mark.asyncio
async def test_kie_client_reads_remaining_credits() -> None:
    client = KieClient("test-key")
    fake = _FakeKieHttpClient({"code": 200, "msg": "success", "data": 0})
    client._client = fake  # type: ignore[attr-defined]

    balance = await client.get_remaining_credits()

    assert fake.calls == ["/api/v1/chat/credit"]
    assert balance.credits == Decimal("0")


@pytest.mark.asyncio
async def test_kie_client_rejects_invalid_credit_response() -> None:
    client = KieClient("test-key")
    client._client = _FakeKieHttpClient({"code": 200, "msg": "success", "data": "bad"})  # type: ignore[attr-defined]

    with pytest.raises(KieProviderError, match="invalid balance"):
        await client.get_remaining_credits()


@pytest.mark.asyncio
async def test_kie_credit_alert_sends_once_to_bootstrap_admins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "kie_credit_alert_enabled", True)
    monkeypatch.setattr(settings, "kie_api_key", "test-key")
    monkeypatch.setattr(settings, "bot_token", "test-bot")
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "100, 200")
    monkeypatch.setattr(settings, "kie_credit_alert_threshold", Decimal("0"))
    monkeypatch.setattr(settings, "kie_credit_alert_repeat_seconds", 3600)

    redis = _FakeRedis()
    bot = _FakeBot()
    credits = await KieCreditAlertService.check_once(
        redis=redis,  # type: ignore[arg-type]
        bot=bot,  # type: ignore[arg-type]
        client=_FakeCreditClient(Decimal("0")),  # type: ignore[arg-type]
    )

    assert credits == Decimal("0")
    assert redis.set_calls == [(ALERT_STATE_KEY, "depleted", 3600)]
    assert [chat_id for chat_id, _text in bot.messages] == [100, 200]
    assert "Остаток кредитов Kie: 0" in bot.messages[0][1]

    await KieCreditAlertService.check_once(
        redis=redis,  # type: ignore[arg-type]
        bot=bot,  # type: ignore[arg-type]
        client=_FakeCreditClient(Decimal("0")),  # type: ignore[arg-type]
    )

    assert len(bot.messages) == 2


@pytest.mark.asyncio
async def test_kie_credit_alert_sends_recovery_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "kie_credit_alert_enabled", True)
    monkeypatch.setattr(settings, "kie_api_key", "test-key")
    monkeypatch.setattr(settings, "bot_token", "test-bot")
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "100")
    monkeypatch.setattr(settings, "kie_credit_alert_threshold", Decimal("10"))

    redis = _FakeRedis("low")
    bot = _FakeBot()
    await KieCreditAlertService.check_once(
        redis=redis,  # type: ignore[arg-type]
        bot=bot,  # type: ignore[arg-type]
        client=_FakeCreditClient(Decimal("11")),  # type: ignore[arg-type]
    )

    assert redis.deleted == [ALERT_STATE_KEY]
    assert bot.messages == [(100, "✅ Kie credits recovered\n\nТекущий остаток кредитов Kie: 11")]


def test_kie_credit_alert_worker_is_wired_into_runtime_contract() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    health = (ROOT / "app" / "api" / "health.py").read_text(encoding="utf-8")
    observability = (ROOT / "docs" / "OBSERVABILITY.md").read_text(encoding="utf-8")

    assert "kie-credit-alert-worker:" in compose
    assert "python -m app.workers.kie_credit_alerts" in compose
    assert 'worker_health(request.app.state.redis, "kie-credit-alert-worker")' in health
    assert "observability:worker:kie-credit-alert-worker:heartbeat" in observability
