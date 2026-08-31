from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_partner_wallet_reuses_idempotency_key_for_same_withdrawal_intent() -> None:
    page = (ROOT / "frontend/mini-app/app/partner-wallet/page.tsx").read_text(encoding="utf-8")

    assert "withdrawalIntentRef" in page
    assert "customerIdempotencyKey()" in page
    assert 'headers: { "Idempotency-Key": idempotencyKey }' in page
    assert "fingerprint" in page
    assert "withdrawalIntentRef.current = null" in page
