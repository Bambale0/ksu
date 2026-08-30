from pathlib import Path

import pytest

from app.api.v1.payments import list_yookassa_packages
from app.core.config import settings


ROOT = Path(__file__).resolve().parents[1]
PAYMENTS_PAGE = ROOT / "frontend" / "mini-app" / "app" / "payments" / "page.tsx"
ENV_EXAMPLE = ROOT / ".env.example"


@pytest.mark.asyncio
async def test_yookassa_catalog_exposes_configured_rub_rox_packages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "rox_packages_json",
        '{"starter":{"amount":"300","credits":"300","currency":"RUB"}}',
    )
    monkeypatch.setattr(settings, "yookassa_shop_id", "shop-id")
    monkeypatch.setattr(settings, "yookassa_secret_key", "secret-key")
    monkeypatch.setattr(settings, "payment_return_url", "https://roxy.example/mini-app/payments/")
    monkeypatch.setattr(settings, "public_base_url", "")

    catalog = await list_yookassa_packages()

    assert catalog["provider"] == "yookassa"
    assert catalog["label"] == "ЮKassa"
    assert catalog["configured"] is True
    assert catalog["currencies"] == ["RUB"]
    assert catalog["packages"] == {
        "starter": {
            "credits": "300",
            "bonus_credits": "0",
            "total_credits": "300",
            "prices": {"RUB": "300"},
        }
    }


@pytest.mark.asyncio
async def test_yookassa_catalog_hides_incomplete_checkout_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "rox_packages_json",
        '{"starter":{"amount":"300","credits":"300","currency":"RUB"}}',
    )
    monkeypatch.setattr(settings, "yookassa_shop_id", "shop-id")
    monkeypatch.setattr(settings, "yookassa_secret_key", "secret-key")
    monkeypatch.setattr(settings, "payment_return_url", "")
    monkeypatch.setattr(settings, "public_base_url", "")

    catalog = await list_yookassa_packages()

    assert catalog["configured"] is False


def test_mini_app_exposes_yookassa_checkout_and_reconciliation() -> None:
    page = PAYMENTS_PAGE.read_text(encoding="utf-8")
    for token in (
        '"yookassa"',
        '"/api/v1/payments/yookassa/packages"',
        'provider: "yookassa"',
        '/api/v1/payments/yookassa/${encodeURIComponent(payment.id)}/reconcile',
        'payment.provider === "yookassa"',
        '>ЮKassa</button>',
    ):
        assert token in page


def test_yookassa_env_example_documents_webhook_endpoint() -> None:
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "/webhooks/payments/yookassa" in env_example
    assert "YOOKASSA_SHOP_ID=" in env_example
    assert "YOOKASSA_SECRET_KEY=" in env_example
