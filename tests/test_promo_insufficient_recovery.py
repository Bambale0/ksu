from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.generations import CreateGenerationRequest, create_generation
from app.api.v1.promocodes import RedeemPromoRequest, redeem
from app.db.models import Notification, PromoCode, User, Wallet, WalletTransaction
from app.db.session import SessionFactory
from app.services.generations import GenerationService
from app.services.wallet import InsufficientBalanceError, WalletService

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


@pytest.mark.asyncio
async def test_wallet_insufficient_error_exposes_authoritative_amounts() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=950000000000001, first_name="Low balance")
        session.add(user)
        await session.flush()
        session.add(Wallet(user_id=user.id, balance=Decimal("2.50")))
        await session.commit()

        with pytest.raises(InsufficientBalanceError) as raised:
            await WalletService.debit(
                session,
                user_id=user.id,
                amount=Decimal("7.00"),
                kind="generation",
            )
        error = raised.value
        assert error.current_balance == Decimal("2.50")
        assert error.required_amount == Decimal("7.00")
        assert error.shortage == Decimal("4.50")
        assert not isinstance(error, ValueError)

        wallet = await session.get(Wallet, user.id)
        assert wallet is not None
        assert wallet.balance == Decimal("2.50")


@pytest.mark.asyncio
async def test_generation_insufficient_balance_reaches_409_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_create(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise InsufficientBalanceError(
            current_balance=Decimal("1.00"),
            required_amount=Decimal("5.00"),
        )

    monkeypatch.setattr(GenerationService, "create", fake_create)
    async with SessionFactory() as session:
        user = User(telegram_id=950000000000002, first_name="Admission")
        session.add(user)
        await session.commit()

        with pytest.raises(HTTPException) as raised:
            await create_generation(
                CreateGenerationRequest(model_id="server-priced-model"),
                user,
                session,
                None,  # type: ignore[arg-type]
            )
        assert raised.value.status_code == 409
        assert raised.value.detail == "Insufficient credits"


@pytest.mark.asyncio
async def test_promo_redemption_updates_wallet_ledger_and_notification() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=950000000000003, first_name="Promo")
        promo = PromoCode(
            code="WELCOME25",
            reward_amount=Decimal("25.00"),
            max_uses=100,
            uses_count=0,
            is_active=True,
        )
        session.add_all([user, promo])
        await session.commit()

        result = await redeem(RedeemPromoRequest(code=" welcome25 "), user, session)
        assert result["status"] == "ok"
        assert Decimal(result["reward_rox"]) == Decimal("25.00")
        assert Decimal(result["balance_rox"]) == Decimal("25.00")

        wallet = await session.get(Wallet, user.id)
        assert wallet is not None
        assert wallet.balance == Decimal("25.00")
        transaction = await session.scalar(
            select(WalletTransaction).where(
                WalletTransaction.user_id == user.id,
                WalletTransaction.kind == "promo_bonus",
            )
        )
        assert transaction is not None
        assert transaction.amount == Decimal("25.00")
        notification = await session.scalar(
            select(Notification).where(
                Notification.user_id == user.id,
                Notification.kind == "promo_redeemed",
            )
        )
        assert notification is not None
        assert notification.title == "Промокод применён"

        with pytest.raises(HTTPException) as reused:
            await redeem(RedeemPromoRequest(code="WELCOME25"), user, session)
        assert reused.value.status_code == 400
        assert reused.value.detail["code"] == "already_used"


@pytest.mark.asyncio
async def test_expired_and_invalid_promos_return_stable_error_codes() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=950000000000004, first_name="Promo errors")
        expired = PromoCode(
            code="OLD",
            reward_amount=Decimal("5.00"),
            max_uses=None,
            uses_count=0,
            is_active=True,
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        session.add_all([user, expired])
        await session.commit()

        with pytest.raises(HTTPException) as expired_error:
            await redeem(RedeemPromoRequest(code="OLD"), user, session)
        assert expired_error.value.detail["code"] == "expired"

        with pytest.raises(HTTPException) as invalid_error:
            await redeem(RedeemPromoRequest(code="NO-SUCH-CODE"), user, session)
        assert invalid_error.value.detail["code"] == "invalid"


def test_promo_recovery_client_uses_server_balance_quote_and_explicit_retry() -> None:
    script = (MINI / "promo-recovery.js").read_text(encoding="utf-8")
    for token in (
        'payload?.detail !== "Insufficient credits"',
        'api("/api/v1/me")',
        'api("/api/v1/generations/quote"',
        "insufficientCurrent",
        "insufficientRequired",
        "insufficientShortage",
        '"Пополнить"',
        '"Отмена"',
        '"Вернуться к генерации"',
        "нажмите «Создать» снова",
        'api("/api/v1/promocodes/redeem"',
        "result.balance_rox",
        "Операций пока нет. Пополните баланс или создайте первый контент.",
        'headers["X-Telegram-Init-Data"] = tg.initData',
    ):
        assert token in script, token

    # The recovery module observes the failed request and fetches quote/balance;
    # it never creates a replacement generation by itself.
    assert 'api("/api/v1/generations", {' not in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "initDataUnsafe" not in script


def test_promo_recovery_module_is_mounted_and_checked_by_ci() -> None:
    integration = (MINI / "shell-integration.js").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'stylesheet.href = "/mini-app/promo-recovery.css"' in integration
    assert 'script.src = "/mini-app/promo-recovery.js"' in integration
    assert "node --check app/web/mini_app/promo-recovery.js" in workflow
    assert (MINI / "promo-recovery.css").is_file()
