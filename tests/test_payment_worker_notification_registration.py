from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from app.workers import payments


def test_payment_worker_registers_notification_events_before_loop(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        payments,
        "register_notification_events",
        lambda: calls.append("register"),
    )

    def fake_asyncio_run(coro: Coroutine[Any, Any, Any]) -> None:
        calls.append("run")
        coro.close()

    monkeypatch.setattr(payments.asyncio, "run", fake_asyncio_run)

    payments.main()

    assert calls == ["register", "run"]
