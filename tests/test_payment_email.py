from __future__ import annotations

from pathlib import Path

import pytest

from app.services.payment_email import normalize_billing_email, validate_billing_email

ROOT = Path(__file__).resolve().parents[1]


def test_billing_email_normalizes_mobile_keyboard_specials() -> None:
    value = " Ksenya\u2011Korkina9411\uff20Mail\uff0eRu\u200b "

    assert normalize_billing_email(value) == "ksenya-korkina9411@mail.ru"
    assert validate_billing_email(value) == "ksenya-korkina9411@mail.ru"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("buyer_test@mail.ru", "buyer_test@mail.ru"),
        ("buyer.test@mail.ru", "buyer.test@mail.ru"),
        ("buyer-test@mail.ru", "buyer-test@mail.ru"),
        ("buyer+test@mail.ru", "buyer+test@mail.ru"),
        ("buyer%tag@mail.ru", "buyer%tag@mail.ru"),
        ("buyer@test\u3002ru", "buyer@test.ru"),
    ],
)
def test_billing_email_normalizes_common_unicode_lookalikes(raw: str, expected: str) -> None:
    assert validate_billing_email(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "ксения@mail.ru",
        "buyer🙂@mail.ru",
        "buyer @mail.ru",
        ".buyer@mail.ru",
        "buyer.@mail.ru",
        "buyer..test@mail.ru",
        "buyer@mail",
    ],
)
def test_billing_email_rejects_non_lava_safe_values(raw: str) -> None:
    with pytest.raises(ValueError, match="email"):
        validate_billing_email(raw)


def test_card_checkout_endpoint_normalizes_before_payment_creation() -> None:
    source = (ROOT / "app" / "api" / "v1" / "card_payments.py").read_text(
        encoding="utf-8"
    )

    assert "validate_billing_email(payload.billing_email)" in source
    assert "billing_email=billing_email" in source
