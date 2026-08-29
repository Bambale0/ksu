from pathlib import Path


API = Path("app/api/v1/payments.py")
PAYMENTS_UI = Path("frontend/mini-app/app/payments/page.tsx")
WALLET_UI = Path("frontend/mini-app/components/wallet-parity.tsx")


def test_cryptobot_is_primary_crypto_checkout_while_2328_remains_available() -> None:
    api_source = API.read_text(encoding="utf-8")

    assert "from app.services.crypto_payments import CryptoBotPaymentService" in api_source
    assert '@router.get("/crypto/packages")' in api_source
    assert "packages = await CryptoBotPaymentService.provider_packages()" in api_source
    assert "payment = await CryptoBotPaymentService.create(" in api_source
    assert '@router.post("/crypto/{payment_id}/reconcile")' in api_source
    assert "payment.provider != CryptoBotPaymentService.PROVIDER" in api_source

    assert '@router.get("/crypto/2328/packages")' in api_source
    assert '@router.post("/crypto/2328/checkout"' in api_source
    assert '@router.post("/crypto/2328/{payment_id}/reconcile")' in api_source
    assert "payment = await Payment2328Service.create(" in api_source
    assert "payment = await Payment2328Service.reconcile(" in api_source


def test_customer_ui_shows_cryptobot_before_2328() -> None:
    payments_source = PAYMENTS_UI.read_text(encoding="utf-8")
    wallet_source = WALLET_UI.read_text(encoding="utf-8")

    assert 'type Provider = "card" | "cryptobot" | "2328"' in payments_source
    assert '"/api/v1/payments/crypto/packages"' in payments_source
    assert '"/api/v1/payments/crypto/2328/packages"' in payments_source
    assert '"/api/v1/payments/crypto/checkout"' in payments_source
    assert '"/api/v1/payments/crypto/2328/checkout"' in payments_source
    assert "CryptoBot" in payments_source
    assert "2328" in payments_source
    assert payments_source.index(">CryptoBot</button>") < payments_source.index(">2328</button>")

    assert '"/api/v1/payments/crypto/packages"' in wallet_source
    assert '"/api/v1/payments/crypto/2328/packages"' in wallet_source
    assert "/mini-app/payments/?provider=cryptobot" in wallet_source
    assert "/mini-app/payments/?provider=2328" in wallet_source
    assert wallet_source.index("Оплатить через CryptoBot") < wallet_source.index("Оплатить через 2328")
