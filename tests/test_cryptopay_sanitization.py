"""Crypto Pay error boundary: never leak upstream HTML in application logs."""

from decimal import Decimal

import httpx
import pytest

from app.providers.payments import CryptoPayClient, PaymentProviderError


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [500, 520])
@pytest.mark.parametrize("operation", ["lookup", "recover", "create"])
async def test_cryptopay_upstream_html_error_is_not_exposed(
    status: int, operation: str,
) -> None:
    private_html = "<!DOCTYPE html><title>temporary provider outage</title> sensitive-payload"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=private_html, request=request)

    client = CryptoPayClient("synthetic-token")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://provider.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(PaymentProviderError) as error:
            if operation == "lookup":
                await client.get_invoice("synthetic-invoice")
            elif operation == "recover":
                await client.find_invoice_by_payload("synthetic-local-id")
            else:
                await client.create_payment(
                    local_id="synthetic-local-id",
                    amount=Decimal("100"),
                    currency="RUB",
                    description="synthetic",
                )
        assert f"HTTP {status}" in str(error.value)
        assert "sensitive-payload" not in str(error.value)
        assert "<!DOCTYPE" not in str(error.value)
    finally:
        await client.aclose()
