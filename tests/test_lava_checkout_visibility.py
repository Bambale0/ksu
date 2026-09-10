from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_yookassa_is_primary_and_lava_is_reserve_for_new_mini_app_checkout() -> None:
    source = (ROOT / "frontend/mini-app/app/payments/page.tsx").read_text(encoding="utf-8")
    quick_wallet = (ROOT / "frontend/mini-app/components/wallet-parity.tsx").read_text(encoding="utf-8")

    assert 'customerRequest<PackageResponse>("/api/v1/payments/card/packages")' in source
    assert 'customerRequest<PackageResponse>("/api/v1/payments/crypto/packages")' not in source
    assert 'customerRequest<PackageResponse>("/api/v1/payments/crypto/2328/packages")' not in source
    assert '>Lava Top · резерв</button>' in source
    assert '>CryptoBot</button>' not in source
    assert '>2328</button>' not in source
    assert '>ЮKassa</button>' in source
    assert 'copy="ЮKassa — основной способ оплаты. Lava Top доступна как резерв, если основной способ временно не проходит."' in source
    assert 'if (requested === "card") return "card";' in source
    assert 'return "yookassa";' in source
    assert '/api/v1/payments/card/packages' not in quick_wallet
    assert '/api/v1/payments/crypto/packages' not in quick_wallet
    assert '/api/v1/payments/crypto/2328/packages' not in quick_wallet
    assert '/api/v1/payments/yookassa/packages' in quick_wallet
    assert 'Резервная оплата · Lava Top' in quick_wallet
    assert '/mini-app/payments/?provider=card' in quick_wallet

    root_api = (ROOT / "frontend/mini-app/lib/api.ts").read_text(encoding="utf-8")
    root_wallet = (ROOT / "frontend/mini-app/components/roxy-app.tsx").read_text(encoding="utf-8")
    social_wallet = (ROOT / "frontend/mini-app/components/roxy-social-app.tsx").read_text(encoding="utf-8")
    assert '"/api/v1/payments/yookassa/packages"' in root_api
    assert '"/api/v1/payments/card/packages"' not in root_api
    assert '"/api/v1/payments/card/checkout"' not in root_api
    assert 'body: JSON.stringify({ provider: "yookassa", package_id: packageId })' in root_api
    for wallet in (root_wallet, social_wallet):
        assert '>ЮKassa</button>' in wallet
        assert '>Оплата картой</button>' not in wallet
        assert 'api.createPayment(selected, currency, email)' not in wallet
        assert 'placeholder="Email без + и дефиса"' not in wallet


def test_historical_hidden_provider_payments_remain_readable() -> None:
    source = (ROOT / "frontend/mini-app/app/payments/page.tsx").read_text(encoding="utf-8")

    assert 'item.provider === "card"' in source
    assert 'item.provider === CRYPTOBOT_PROVIDER' in source
    assert 'item.provider === "2328"' in source
    assert 'return "Lava Top";' in source
    assert 'return "CryptoBot";' in source
