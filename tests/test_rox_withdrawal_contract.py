from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_cash_withdrawal_contract_is_referral_rub_only() -> None:
    api = _read("app/api/v1/referrals.py")
    partner = _read("app/services/partner.py")
    referrals = _read("app/services/referrals.py")
    page = _read("frontend/mini-app/app/partner-wallet/page.tsx")

    assert '"withdrawable_rub"' in api
    assert '"pending_referral_rub"' in api
    assert '"partner_total_earned_rub"' in api
    assert '"withdrawable_rox"' not in api
    assert '"amount_rub"' in api

    # Cash accounting is built from referral rewards, not from the user's ROX wallet.
    assert "ReferralReward.partner_user_id == user_id" in partner
    assert "Wallet" not in partner

    # Referral rewards are calculated from the payment-owned cash basis. Gift ROX
    # credited by a package must not become partner payout income.
    assert "reward_basis = Decimal(payment_amount)" in referrals
    assert "payment_amount=reward_basis" in referrals

    assert "ROX — внутренняя валюта ROXY и на карту не выводится" in page
    assert "только партнёрский процент с реально оплаченных заказов рефералов" in page
    assert "ROX, бонусы и пополнения в вывод не входят" in page
