from decimal import Decimal
from pathlib import Path

import pytest

from app.api.v1.referrals import invitations, stats
from app.core.config import settings
from app.db.models import PartnerWithdrawal, ReferralRelation, ReferralReward, User, WalletTransaction
from app.db.session import SessionFactory
from app.services.partner import PartnerInsufficientFunds, PartnerService, PartnerWithdrawalError

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_partner_withdrawal_reserves_available_income_and_cancel_restores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "partner_min_withdrawal_rub", Decimal("0"))
    async with SessionFactory() as session:
        partner = User(telegram_id=920000000000001, first_name="Partner")
        source = User(telegram_id=920000000000002, first_name="Source")
        session.add_all([partner, source])
        await session.flush()
        source_tx = WalletTransaction(
            user_id=source.id,
            kind="payment_credit",
            amount=Decimal("100.00"),
            balance_before=Decimal("0"),
            balance_after=Decimal("100.00"),
            status="completed",
        )
        session.add(source_tx)
        await session.flush()
        session.add(
            ReferralReward(
                partner_user_id=partner.id,
                source_user_id=source.id,
                source_transaction_id=source_tx.id,
                level=1,
                percent=Decimal("30"),
                amount=Decimal("30.00"),
                status="available",
            )
        )
        await session.commit()

        before = await PartnerService.accounting(session, partner.id)
        assert before["total_earned"] == Decimal("30.00")
        assert before["available"] == Decimal("30.00")

        withdrawal = await PartnerService.create_withdrawal(
            session,
            user_id=partner.id,
            amount=Decimal("20.00"),
            requisites="SBP +7 900 000-00-00",
        )
        await session.commit()
        after = await PartnerService.accounting(session, partner.id)
        assert after["available"] == Decimal("10.00")
        assert after["pending_withdrawals"] == Decimal("20.00")

        with pytest.raises(PartnerInsufficientFunds):
            await PartnerService.create_withdrawal(
                session,
                user_id=partner.id,
                amount=Decimal("11.00"),
                requisites="same",
            )
        await session.rollback()

        canceled = await PartnerService.cancel_withdrawal(
            session,
            user_id=partner.id,
            withdrawal_id=withdrawal.id,
        )
        await session.commit()
        assert canceled.status == "canceled"
        restored = await PartnerService.accounting(session, partner.id)
        assert restored["available"] == Decimal("30.00")
        assert restored["pending_withdrawals"] == Decimal("0")


@pytest.mark.asyncio
async def test_only_pending_withdrawal_can_be_user_canceled() -> None:
    async with SessionFactory() as session:
        partner = User(telegram_id=920000000000003, first_name="Partner2")
        session.add(partner)
        await session.flush()
        item = PartnerWithdrawal(
            user_id=partner.id,
            amount=Decimal("5.00"),
            status="processing",
            requisites={"details": "private"},
        )
        session.add(item)
        await session.commit()
        with pytest.raises(PartnerWithdrawalError):
            await PartnerService.cancel_withdrawal(
                session,
                user_id=partner.id,
                withdrawal_id=item.id,
            )


@pytest.mark.asyncio
async def test_partner_stats_and_invites_preserve_two_line_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "bot_username", "KsuExampleBot")
    async with SessionFactory() as session:
        partner = User(telegram_id=920000000000004, first_name="Root")
        first = User(telegram_id=920000000000005, username="firstline", first_name="First")
        second = User(telegram_id=920000000000006, username="secondline", first_name="Second")
        session.add_all([partner, first, second])
        await session.flush()
        session.add_all(
            [
                ReferralRelation(referred_user_id=first.id, inviter_user_id=partner.id),
                ReferralRelation(referred_user_id=second.id, inviter_user_id=first.id),
            ]
        )
        await session.commit()

        result = await stats(partner, session)
        assert result["first_line"] == 1
        assert result["second_line"] == 1
        assert result["referral_payload"] == f"ref_{partner.telegram_id}"
        assert result["referral_link"] == f"https://t.me/KsuExampleBot?start=ref_{partner.telegram_id}"

        invited = await invitations(partner, session, line=None, limit=50, offset=0)
        assert {item["line"] for item in invited["items"]} == {1, 2}
        assert all("telegram_id" not in item for item in invited["items"])


def test_partner_client_uses_server_accounting_and_validates_before_submit() -> None:
    script = _read("partner.js")
    for token in (
        '"/api/v1/referrals/stats"',
        '"/api/v1/referrals/invitations?limit=50"',
        '"/api/v1/referrals/rewards?limit=50"',
        '"/api/v1/referrals/withdrawals?limit=50"',
        'method: "POST"',
        "minimum_withdrawal",
        "state.stats.available",
        "Сумма больше доступного баланса",
        "navigator.clipboard.writeText",
        'document.execCommand("copy")',
    ):
        assert token in script, token
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "requisites" in script


def test_partner_cabinet_mounts_inside_profile_and_is_checked_by_ci() -> None:
    integration = _read("shell-integration.js")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'document.getElementById("partnerPreview")' in integration
    assert 'script.src = "/mini-app/partner.js"' in integration
    assert "node --check app/web/mini_app/partner.js" in workflow
    assert (MINI / "partner.css").is_file()
