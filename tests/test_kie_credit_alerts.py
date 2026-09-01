from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.providers.kie import KieProviderError
from app.providers.kie_credits import KieCreditClient
from app.services.kie_credit_alerts import (
    ALERT_REPEAT_KEY,
    ALERT_STATE_KEY,
    KieCreditAlertService,
)

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload: object, *, status_error: Exception | None = None) -> None:
        self.payload = payload
        self.status_error = status_error

    def raise_for_status(self) -> None:
        if self.status_error:
            raise self.status_error

    def json(self) -> object:
        return self.payload


class FakeHttpClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.paths: list[str] = []

    async def get(self, path: str) -> FakeResponse:
        self.paths.append(path)
        return FakeResponse(self.payload)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int | None = None) -> None:
        del ex
        self.values[key] = value

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            deleted += int(key in self.values)
            self.values.pop(key, None)
        return deleted


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


class FakeCreditClient:
    def __init__(self, credits: Decimal) -> None:
        self.credits = credits

    async def get_remaining_credits(self) -> SimpleNamespace:
        return SimpleNamespace(credits=self.credits)


@pytest.mark.asyncio
async def test_kie_credit_provider_uses_documented_common_api_contract() -> None:
    client = KieCreditClient.__new__(KieCreditClient)
    fake = FakeHttpClient({"code": 200, "msg": "success", "data": 123.5})
    client._client = fake  # type: ignore[attr-defined]

    balance = await client.get_remaining_credits()

    assert fake.paths == ["/api/v1/chat/credit"]
    assert balance.credits == Decimal("123.5")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"code": 500, "msg": "failed", "data": 100},
        {"code": "nope", "data": 100},
        {"code": 200, "data": None},
        {"code": 200, "data": True},
        {"code": 200, "data": -1},
        {"code": 200, "data": "NaN"},
    ],
)
async def test_kie_credit_provider_rejects_invalid_provider_payloads(payload: object) -> None:
    client = KieCreditClient.__new__(KieCreditClient)
    client._client = FakeHttpClient(payload)  # type: ignore[attr-defined]

    with pytest.raises(KieProviderError):
        await client.get_remaining_credits()


def test_kie_credit_format_preserves_integer_trailing_zeroes() -> None:
    assert KieCreditAlertService._format_credits(Decimal("500")) == "500"
    assert KieCreditAlertService._format_credits(Decimal("500.00")) == "500"
    assert KieCreditAlertService._format_credits(Decimal("123.50")) == "123.5"


@pytest.mark.asyncio
async def test_kie_credit_alert_transitions_repeat_and_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "kie_credit_alert_threshold", Decimal("500"))
    monkeypatch.setattr(settings, "kie_credit_alert_repeat_seconds", 3600)

    async def recipients(_cls: type[KieCreditAlertService], _session: object) -> list[int]:
        return [101, 202]

    monkeypatch.setattr(KieCreditAlertService, "recipient_ids", classmethod(recipients))

    redis = FakeRedis()
    bot = FakeBot()
    client = FakeCreditClient(Decimal("400"))

    await KieCreditAlertService.check_once(
        session=object(),  # type: ignore[arg-type]
        redis=redis,  # type: ignore[arg-type]
        bot=bot,  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
    )
    assert len(bot.messages) == 2
    assert all("мало кредитов" in text for _, text in bot.messages)
    assert redis.values[ALERT_STATE_KEY] == "low"
    assert redis.values[ALERT_REPEAT_KEY] == "low"

    # Same state is deduplicated while the repeat marker exists.
    await KieCreditAlertService.check_once(
        session=object(),  # type: ignore[arg-type]
        redis=redis,  # type: ignore[arg-type]
        bot=bot,  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
    )
    assert len(bot.messages) == 2

    # Expired repeat marker produces a reminder without losing state.
    await redis.delete(ALERT_REPEAT_KEY)
    await KieCreditAlertService.check_once(
        session=object(),  # type: ignore[arg-type]
        redis=redis,  # type: ignore[arg-type]
        bot=bot,  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
    )
    assert len(bot.messages) == 4

    # A stronger state transition alerts immediately even if repeat is active.
    client.credits = Decimal("0")
    await KieCreditAlertService.check_once(
        session=object(),  # type: ignore[arg-type]
        redis=redis,  # type: ignore[arg-type]
        bot=bot,  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
    )
    assert len(bot.messages) == 6
    assert all("кредиты закончились" in text for _, text in bot.messages[-2:])
    assert redis.values[ALERT_STATE_KEY] == "depleted"

    # Recovery survives repeat-TTL semantics because alert state is persistent.
    client.credits = Decimal("900")
    await KieCreditAlertService.check_once(
        session=object(),  # type: ignore[arg-type]
        redis=redis,  # type: ignore[arg-type]
        bot=bot,  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
    )
    assert len(bot.messages) == 8
    assert all("баланс восстановлен" in text for _, text in bot.messages[-2:])
    assert ALERT_STATE_KEY not in redis.values
    assert ALERT_REPEAT_KEY not in redis.values


def test_kie_credit_alert_recipients_are_db_admins_not_bootstrap_ids() -> None:
    source = (ROOT / "app/services/kie_credit_alerts.py").read_text(encoding="utf-8")
    assert "AdminAccount.is_active.is_(True)" in source
    assert "User.is_active.is_(True)" in source
    assert 'frozenset({"owner", "admin", "finance"})' in source
    assert "admin_bootstrap_telegram_ids" not in source
    assert "parse_bootstrap_ids" not in source


def test_kie_credit_worker_is_a_first_class_production_service() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    health = (ROOT / "app/api/health.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
    worker = (ROOT / "app/workers/kie_credit_alerts.py").read_text(encoding="utf-8")

    assert "kie-credit-alert-worker:" in compose
    assert 'image: "ksu-app:${KSU_IMAGE_TAG:-local}"' in compose.split(
        "  kie-credit-alert-worker:\n", 1
    )[1].split("\n  backup-worker:", 1)[0]
    assert "command: python -m app.workers.kie_credit_alerts" in compose
    assert '"kie-credit-alert-worker"' in health
    assert "kie-credit-alert-worker" in workflow
    assert 'WORKER_NAME = "kie-credit-alert-worker"' in worker
    assert "record_worker_heartbeat" in worker
