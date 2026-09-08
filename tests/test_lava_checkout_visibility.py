from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_only_yookassa_is_exposed_for_new_mini_app_checkout() -> None:
    source = (ROOT / "frontend/mini-app/app/payments/page.tsx").read_text(encoding="utf-8")
    quick_wallet = (ROOT / "frontend/mini-app/components/wallet-parity.tsx").read_text(encoding="utf-8")

    assert 'customerRequest<PackageResponse>("/api/v1/payments/card/packages")' not in source
    assert 'customerRequest<PackageResponse>("/api/v1/payments/crypto/packages")' not in source
    assert 'customerRequest<PackageResponse>("/api/v1/payments/crypto/2328/packages")' not in source
    assert '>Lava Top</button>' not in source
    assert '>CryptoBot</button>' not in source
    assert '>2328</button>' not in source
    assert '>ЮKassa</button>' in source
    assert 'copy="Пополнение ROX сейчас доступно через ЮKassa."' in source
    assert 'return "yookassa";' in source
    assert '/api/v1/payments/card/packages' not in quick_wallet
    assert '/api/v1/payments/crypto/packages' not in quick_wallet
    assert '/api/v1/payments/crypto/2328/packages' not in quick_wallet
    assert '/api/v1/payments/yookassa/packages' in quick_wallet
    assert 'Пополнить через ЮKassa' in quick_wallet


def test_historical_hidden_provider_payments_remain_readable() -> None:
    source = (ROOT / "frontend/mini-app/app/payments/page.tsx").read_text(encoding="utf-8")

    assert 'item.provider === "card"' in source
    assert 'item.provider === CRYPTOBOT_PROVIDER' in source
    assert 'item.provider === "2328"' in source
    assert 'return "Lava Top";' in source
    assert 'return "CryptoBot";' in source
