from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_lava_is_hidden_from_new_mini_app_checkout() -> None:
    source = (ROOT / "frontend/mini-app/app/payments/page.tsx").read_text(encoding="utf-8")

    assert 'customerRequest<PackageResponse>("/api/v1/payments/card/packages")' not in source
    assert '>Lava Top</button>' not in source
    assert 'copy="Оплатить в рублях можно через ЮKassa.' in source
    assert 'return "yookassa";' in source


def test_historical_lava_payments_remain_readable() -> None:
    source = (ROOT / "frontend/mini-app/app/payments/page.tsx").read_text(encoding="utf-8")

    assert 'item.provider === "card"' in source
    assert 'return "Lava Top";' in source
