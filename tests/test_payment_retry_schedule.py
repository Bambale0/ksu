from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.payment_retry_schedule import PaymentRetrySchedule
from app.services import payment_reconciliation
from app.services.payment_reconciliation import PaymentReconciliationService
from app.services.payments import PaymentService


@pytest.mark.asyncio
async def test_retry_schedule_performs_only_metadata_upsert(monkeypatch):
    clock = __import__("datetime").datetime(2026, 11, 15, tzinfo=__import__("datetime").timezone.utc)
    monkeypatch.setattr("app.services.payment_retry_schedule.utcnow", lambda: clock)
    session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    await PaymentRetrySchedule.record(session, payment_id=uuid4(), attempt_count=3, cooldown_seconds=600, last_error_code="provider_reconcile_exception")
    session.execute.assert_awaited_once()
    stmt = session.execute.await_args.args[0]
    assert "ON CONFLICT" in str(stmt.compile(dialect=__import__("sqlalchemy").dialects.postgresql.dialect()))
    assert clock + timedelta(minutes=10) in [binding.value for binding in stmt._values.values()]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_schedule_rejects_sensitive_error_text():
    with pytest.raises(ValueError):
        await PaymentRetrySchedule.record(None, payment_id=uuid4(), attempt_count=1, cooldown_seconds=60, last_error_code="https://secrets.example/token")
    with pytest.raises(ValueError):
        await PaymentRetrySchedule.record(None, payment_id=uuid4(), attempt_count=1, cooldown_seconds=0)


class _Rows:
    def __init__(self, data):
        self.data = data
    def all(self):
        return self.data


class _ScheduleSession:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return None
    async def execute(self, statement):
        return _Rows(self.rows)
    async def scalar(self, statement):
        return "pending"


@pytest.mark.asyncio
async def test_durable_reconciliation_resumes_exponential_backoff_after_restart(monkeypatch):
    payment_id=uuid4()
    sessions=[]
    def factory():
        s=_ScheduleSession([(payment_id,"cryptobot","inv",4)])
        sessions.append(s)
        return s
    monkeypatch.setattr(payment_reconciliation,"SessionFactory",factory)
    monkeypatch.setattr(PaymentService,"provider_configured",lambda provider:True)
    monkeypatch.setattr(PaymentReconciliationService,"_retry_after",{})
    monkeypatch.setattr(PaymentReconciliationService,"_failure_counts",{})
    monkeypatch.setattr(payment_reconciliation.random,"uniform",lambda *_:1.0)
    async def fail(*args,**kwargs):
        raise RuntimeError("fake outage")
    monkeypatch.setattr(PaymentService,"reconcile",fail)
    saved=[]
    async def record(session,**kwargs):
        saved.append(kwargs)
    monkeypatch.setattr(payment_reconciliation.PaymentRetrySchedule,"record",record)
    assert await PaymentReconciliationService.run_once(durable=True)==0
    assert saved[0]["attempt_count"]==5
    assert saved[0]["cooldown_seconds"]==960


@pytest.mark.asyncio
async def test_durable_no_change_schedules_backoff_without_settling(monkeypatch):
    payment_id=uuid4()
    monkeypatch.setattr(payment_reconciliation,"SessionFactory",lambda:_ScheduleSession([(payment_id,"cryptobot","inv",0)]))
    monkeypatch.setattr(PaymentService,"provider_configured",lambda provider:True)
    monkeypatch.setattr(PaymentReconciliationService,"_retry_after",{})
    monkeypatch.setattr(PaymentReconciliationService,"_failure_counts",{})
    monkeypatch.setattr(PaymentService,"reconcile",AsyncMock())
    saved=[]
    async def record(session,**kwargs):
        saved.append(kwargs)
    monkeypatch.setattr(payment_reconciliation.PaymentRetrySchedule,"record",record)
    assert await PaymentReconciliationService.run_once(durable=True)==1
    assert saved[0]["cooldown_seconds"]==900
    assert saved[0]["attempt_count"]==0