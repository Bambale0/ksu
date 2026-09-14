from decimal import Decimal
import uuid

import pytest

from app.db.models import Payment, PromoCode
from app.services.payment_bonuses import TopUpBonusService
from app.services.payment_creation import PaymentCreationLifecycle
from app.services.promocodes import PromoCodeService


@pytest.mark.parametrize(
    ("base", "gift", "total"),
    [
        ("100", "10.00", "110.00"),
        ("300", "30.00", "330.00"),
        ("500", "50.00", "550.00"),
        ("1000", "100.00", "1100.00"),
        ("1500", "150.00", "1650.00"),
        ("2000", "200.00", "2200.00"),
    ],
)
def test_package_gift_is_ten_percent(base: str, gift: str, total: str) -> None:
    assert TopUpBonusService.bonus_for(base) == Decimal(gift)
    assert TopUpBonusService.total_for(base) == Decimal(total)


def test_payment_creation_snapshots_package_gift() -> None:
    payment = Payment(
        user_id=uuid.uuid4(),
        provider="yookassa",
        amount=Decimal("300"),
        currency="RUB",
        rox_amount=Decimal("300"),
        status="creating",
        payload={
            "package_id": "p300",
            "request_key": str(uuid.uuid4()),
            "base_credits": "300",
            "bonus_credits": "0",
            "credited_credits": "300",
        },
    )

    PaymentCreationLifecycle._apply_package_bonus(payment)

    assert payment.rox_amount == Decimal("330.00")
    assert payment.payload["base_credits"] == "300"
    assert payment.payload["package_bonus_credits"] == "30.00"
    assert payment.payload["bonus_credits"] == "30.00"
    assert payment.payload["credited_credits"] == "330.00"


def test_promo_bonus_stacks_on_top_of_package_gift() -> None:
    payment = Payment(
        user_id=uuid.uuid4(),
        provider="yookassa",
        amount=Decimal("1000"),
        currency="RUB",
        rox_amount=Decimal("1100"),
        status="pending",
        payload={
            "package_id": "p1000",
            "request_key": str(uuid.uuid4()),
            "base_credits": "1000",
            "package_bonus_credits": "100",
            "bonus_credits": "100",
            "credited_credits": "1100",
        },
    )
    promo = PromoCode(
        code="STACK50",
        reward_amount=Decimal("50"),
        max_uses=100,
        uses_count=0,
        is_active=True,
    )

    PromoCodeService._attach_payload(payment, promo)

    assert payment.payload["promo_reward_credits"] == "50"
    assert payment.payload["bonus_credits"] == "150"
    assert payment.payload["credited_credits"] == "1150"


def test_product_promo_minimum_is_1000_rox() -> None:
    assert PromoCodeService.MIN_PROMO_BASE_CREDITS == Decimal("1000")
