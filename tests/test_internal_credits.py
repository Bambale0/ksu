from decimal import Decimal

import pytest

from app.core.config import settings
from app.services.credits import InternalCreditService
from app.services.payments import PaymentService


def test_internal_credit_is_ten_rubles() -> None:
    previous = settings.internal_credit_rub
    settings.internal_credit_rub = Decimal("10")
    try:
        assert InternalCreditService.rub_per_credit() == Decimal("10")
        assert InternalCreditService.rubles_for("1") == Decimal("10.00")
        assert InternalCreditService.rubles_for("8.5") == Decimal("85.00")
        assert InternalCreditService.credits_for("300") == Decimal("30.00")
    finally:
        settings.internal_credit_rub = previous


def test_payment_package_can_derive_rub_amount_from_credits() -> None:
    previous_rate = settings.internal_credit_rub
    previous_packages = settings.rox_packages_json
    settings.internal_credit_rub = Decimal("10")
    settings.rox_packages_json = '{"starter":{"credits":"30","currency":"RUB"}}'
    try:
        package = PaymentService.package("starter")
        assert package.credits == Decimal("30")
        assert package.amount == Decimal("300.00")
    finally:
        settings.internal_credit_rub = previous_rate
        settings.rox_packages_json = previous_packages


def test_payment_package_rejects_rate_mismatch() -> None:
    previous_rate = settings.internal_credit_rub
    previous_packages = settings.rox_packages_json
    settings.internal_credit_rub = Decimal("10")
    settings.rox_packages_json = (
        '{"broken":{"amount":"299","credits":"30","currency":"RUB"}}'
    )
    try:
        with pytest.raises(ValueError, match="violates internal credit rate"):
            PaymentService.packages()
    finally:
        settings.internal_credit_rub = previous_rate
        settings.rox_packages_json = previous_packages


def test_legacy_rox_package_remains_compatible_when_rate_matches() -> None:
    previous_rate = settings.internal_credit_rub
    previous_packages = settings.rox_packages_json
    settings.internal_credit_rub = Decimal("10")
    settings.rox_packages_json = '{"legacy":{"amount":"100","rox":"10","currency":"RUB"}}'
    try:
        package = PaymentService.package("legacy")
        assert package.credits == Decimal("10")
        assert package.amount == Decimal("100")
    finally:
        settings.internal_credit_rub = previous_rate
        settings.rox_packages_json = previous_packages
