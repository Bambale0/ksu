import base64
import hashlib
import hmac
import time

import pytest

from app.core.config import settings
from app.providers.kie import verify_kie_webhook
from app.providers.payments import CryptoPayClient, make_tbank_token
from app.services.payments import PaymentService


@pytest.mark.asyncio
async def test_cryptopay_webhook_signature() -> None:
    token = "12345:test-token"
    body = b'{"update_type":"invoice_paid","payload":{"invoice_id":42}}'
    secret = hashlib.sha256(token.encode()).digest()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()

    client = CryptoPayClient(token, "https://example.invalid")
    try:
        assert client.verify_webhook(body, signature)
        assert not client.verify_webhook(body + b" ", signature)
    finally:
        await client.aclose()


def test_kie_webhook_signature() -> None:
    key = "kie-webhook-secret"
    task_id = "task_123"
    timestamp = str(int(time.time()))
    digest = hmac.new(
        key.encode(),
        f"{task_id}.{timestamp}".encode(),
        hashlib.sha256,
    ).digest()
    signature = base64.b64encode(digest).decode()

    assert verify_kie_webhook(
        task_id=task_id,
        timestamp=timestamp,
        signature=signature,
        hmac_key=key,
    )
    assert not verify_kie_webhook(
        task_id="task_other",
        timestamp=timestamp,
        signature=signature,
        hmac_key=key,
    )


def test_tbank_token_uses_only_root_values() -> None:
    payload = {
        "TerminalKey": "Terminal",
        "Amount": 19200,
        "OrderId": "00000",
        "Description": "Test",
        "DATA": {"Email": "ignored@example.com"},
    }
    password = "secret"
    source = "19200Test00000secretTerminal"
    expected = hashlib.sha256(source.encode()).hexdigest()
    assert make_tbank_token(payload, password) == expected


def test_rox_packages_are_server_side(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "rox_packages_json",
        '{"starter":{"amount":"299.00","currency":"RUB","rox":"350"}}',
    )
    package = PaymentService.package("starter")
    assert str(package.amount) == "299.00"
    assert str(package.rox_amount) == "350"
    assert package.currency == "RUB"
