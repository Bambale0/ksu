from __future__ import annotations

import asyncio
import random
import uuid
from pathlib import Path

import pytest
from aiogram.types import User as TelegramUser
from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import ReferralRelation, User, Wallet
from app.db.referral_models import ReferralEvent
from app.db.session import SessionFactory
from app.services.users import UserService

ROOT = Path(__file__).resolve().parents[1]


def _telegram_user(name: str) -> TelegramUser:
    return TelegramUser(
        id=96_000_000_000_000 + random.randint(1, 999_999_999),
        is_bot=False,
        first_name=name,
    )


async def _create_inviter(name: str = "Inviter") -> tuple[int, uuid.UUID]:
    tg_user = _telegram_user(name)
    async with SessionFactory() as session:
        inviter = await UserService.get_or_create(session, tg_user)
        await session.commit()
        return tg_user.id, inviter.id


def _disable_burst(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "referral_antifraud_burst_max", 0)
    monkeypatch.setattr(settings, "referral_antifraud_burst_window_seconds", 0)


def test_referral_event_model_is_registered_for_alembic_metadata() -> None:
    env_source = (ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "from app.db import referral_models" in env_source
    assert ReferralEvent.__table__.name == "referral_events"
    assert ReferralEvent.__table__.c.metadata is not None


@pytest.mark.asyncio
async def test_hourly_referral_limit_blocks_bonus_without_banning_referrer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "start_balance_rox", 0)
    monkeypatch.setattr(settings, "invite_bonus_rox", 30)
    monkeypatch.setattr(settings, "referral_antifraud_max_per_hour", 1)
    monkeypatch.setattr(settings, "referral_antifraud_max_per_day", 0)
    _disable_burst(monkeypatch)

    inviter_tg_id, inviter_id = await _create_inviter("Hourly")

    async with SessionFactory() as session:
        first = await UserService.get_or_create(
            session,
            _telegram_user("First"),
            inviter_telegram_id=inviter_tg_id,
        )
        await session.commit()
        first_id = first.id

    async with SessionFactory() as session:
        second = await UserService.get_or_create(
            session,
            _telegram_user("Second"),
            inviter_telegram_id=inviter_tg_id,
        )
        await session.commit()
        second_id = second.id

    async with SessionFactory() as session:
        relations = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(ReferralRelation)
                    .where(ReferralRelation.inviter_user_id == inviter_id)
                )
            )
            or 0
        )
        wallet = await session.get(Wallet, inviter_id)
        inviter = await session.get(User, inviter_id)
        reasons = list(
            (
                await session.scalars(
                    select(ReferralEvent.reason).where(
                        ReferralEvent.inviter_user_id == inviter_id
                    )
                )
            ).all()
        )
        referred_ids = set(
            (
                await session.scalars(
                    select(ReferralRelation.referred_user_id).where(
                        ReferralRelation.inviter_user_id == inviter_id
                    )
                )
            ).all()
        )

    assert relations == 1
    assert wallet is not None
    assert wallet.balance == 30
    assert inviter is not None and inviter.is_active is True
    assert sorted(reasons) == ["attached", "hourly_limit"]
    assert first_id in referred_ids
    assert second_id not in referred_ids


@pytest.mark.asyncio
async def test_daily_referral_limit_blocks_bonus_without_banning_referrer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "start_balance_rox", 0)
    monkeypatch.setattr(settings, "invite_bonus_rox", 30)
    monkeypatch.setattr(settings, "referral_antifraud_max_per_hour", 0)
    monkeypatch.setattr(settings, "referral_antifraud_max_per_day", 1)
    _disable_burst(monkeypatch)

    inviter_tg_id, inviter_id = await _create_inviter("Daily")

    async with SessionFactory() as session:
        await UserService.get_or_create(
            session,
            _telegram_user("Daily allowed"),
            inviter_telegram_id=inviter_tg_id,
        )
        await session.commit()

    async with SessionFactory() as session:
        await UserService.get_or_create(
            session,
            _telegram_user("Daily blocked"),
            inviter_telegram_id=inviter_tg_id,
        )
        await session.commit()

    async with SessionFactory() as session:
        inviter = await session.get(User, inviter_id)
        relation_count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(ReferralRelation)
                    .where(ReferralRelation.inviter_user_id == inviter_id)
                )
            )
            or 0
        )
        reasons = list(
            (
                await session.scalars(
                    select(ReferralEvent.reason).where(
                        ReferralEvent.inviter_user_id == inviter_id
                    )
                )
            ).all()
        )

    assert inviter is not None and inviter.is_active is True
    assert relation_count == 1
    assert sorted(reasons) == ["attached", "daily_limit"]


@pytest.mark.asyncio
async def test_burst_threshold_deactivates_referrer_and_blocks_current_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "start_balance_rox", 0)
    monkeypatch.setattr(settings, "invite_bonus_rox", 30)
    monkeypatch.setattr(settings, "referral_antifraud_max_per_hour", 0)
    monkeypatch.setattr(settings, "referral_antifraud_max_per_day", 0)
    monkeypatch.setattr(settings, "referral_antifraud_burst_window_seconds", 10)
    monkeypatch.setattr(settings, "referral_antifraud_burst_max", 2)
    monkeypatch.setattr(settings, "referral_antifraud_burst_autoban", True)

    inviter_tg_id, inviter_id = await _create_inviter("Burst")

    async with SessionFactory() as session:
        await UserService.get_or_create(
            session,
            _telegram_user("Allowed"),
            inviter_telegram_id=inviter_tg_id,
        )
        await session.commit()

    async with SessionFactory() as session:
        blocked = await UserService.get_or_create(
            session,
            _telegram_user("Blocked"),
            inviter_telegram_id=inviter_tg_id,
        )
        await session.commit()
        blocked_id = blocked.id

    async with SessionFactory() as session:
        inviter = await UserService.get_by_telegram_id(session, inviter_tg_id)
        relations = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(ReferralRelation)
                    .where(ReferralRelation.inviter_user_id == inviter_id)
                )
            )
            or 0
        )
        wallet = await session.get(Wallet, inviter_id)
        blocked_relation = await session.get(ReferralRelation, blocked_id)
        events = list(
            (
                await session.scalars(
                    select(ReferralEvent).where(
                        ReferralEvent.inviter_user_id == inviter_id
                    )
                )
            ).all()
        )

    assert inviter is not None
    assert inviter.is_active is False
    assert relations == 1
    assert wallet is not None and wallet.balance == 30
    assert blocked_relation is None
    assert sorted(event.reason for event in events) == ["attached", "burst_autoban"]
    burst_event = next(event for event in events if event.reason == "burst_autoban")
    assert burst_event.details["threshold"] == 2


@pytest.mark.asyncio
async def test_burst_limit_can_reject_without_autoban(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "start_balance_rox", 0)
    monkeypatch.setattr(settings, "invite_bonus_rox", 30)
    monkeypatch.setattr(settings, "referral_antifraud_max_per_hour", 0)
    monkeypatch.setattr(settings, "referral_antifraud_max_per_day", 0)
    monkeypatch.setattr(settings, "referral_antifraud_burst_window_seconds", 10)
    monkeypatch.setattr(settings, "referral_antifraud_burst_max", 2)
    monkeypatch.setattr(settings, "referral_antifraud_burst_autoban", False)

    inviter_tg_id, inviter_id = await _create_inviter("Burst no ban")
    for name in ("Allowed", "Blocked"):
        async with SessionFactory() as session:
            await UserService.get_or_create(
                session,
                _telegram_user(name),
                inviter_telegram_id=inviter_tg_id,
            )
            await session.commit()

    async with SessionFactory() as session:
        inviter = await session.get(User, inviter_id)
        reasons = list(
            (
                await session.scalars(
                    select(ReferralEvent.reason).where(
                        ReferralEvent.inviter_user_id == inviter_id
                    )
                )
            ).all()
        )
    assert inviter is not None and inviter.is_active is True
    assert sorted(reasons) == ["attached", "burst_limit"]


@pytest.mark.asyncio
async def test_concurrent_referrals_are_serialized_under_same_inviter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "start_balance_rox", 0)
    monkeypatch.setattr(settings, "invite_bonus_rox", 30)
    monkeypatch.setattr(settings, "referral_antifraud_max_per_hour", 1)
    monkeypatch.setattr(settings, "referral_antifraud_max_per_day", 0)
    _disable_burst(monkeypatch)

    inviter_tg_id, inviter_id = await _create_inviter("Concurrent")
    visitors = (_telegram_user("Concurrent A"), _telegram_user("Concurrent B"))

    async def register(tg_user: TelegramUser) -> None:
        async with SessionFactory() as session:
            await UserService.get_or_create(
                session,
                tg_user,
                inviter_telegram_id=inviter_tg_id,
            )
            await session.commit()

    await asyncio.gather(*(register(visitor) for visitor in visitors))

    async with SessionFactory() as session:
        relation_count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(ReferralRelation)
                    .where(ReferralRelation.inviter_user_id == inviter_id)
                )
            )
            or 0
        )
        wallet = await session.get(Wallet, inviter_id)
        reasons = list(
            (
                await session.scalars(
                    select(ReferralEvent.reason).where(
                        ReferralEvent.inviter_user_id == inviter_id
                    )
                )
            ).all()
        )

    assert relation_count == 1
    assert wallet is not None
    assert wallet.balance == 30
    assert sorted(reasons) == ["attached", "hourly_limit"]
