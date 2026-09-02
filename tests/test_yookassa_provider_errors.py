from decimal import Decimal

import httpx
import pytest

from app.providers.payments import PaymentProviderError, YooKassaClient


async def _replace_transport(
    client: YooKassaClient,
    handler,
) -> None:
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.yookassa.ru",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_yookassa_create_wraps_http_status_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"type": "error", "description": "invalid credentials"},
            request=request,
        )

    client = YooKassaClient("shop", "secret")
    await _replace_transport(client, handler)
    try:
        with pytest.raises(PaymentProviderError, match=r"HTTP 401"):
            await client.create_payment(
                local_id="00000000-0000-0000-0000-000000000001",
                amount=Decimal("100"),
                currency="RUB",
                description="ROX top-up",
                return_url="https://example.invalid/return",
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_yookassa_create_wraps_transport_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    client = YooKassaClient("shop", "secret")
    await _replace_transport(client, handler)
    try:
        with pytest.raises(PaymentProviderError, match=r"transport failed"):
            await client.create_payment(
                local_id="00000000-0000-0000-0000-000000000002",
                amount=Decimal("100"),
                currency="RUB",
                description="ROX top-up",
                return_url="https://example.invalid/return",
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_yookassa_create_wraps_invalid_json() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json", request=request)

    client = YooKassaClient("shop", "secret")
    await _replace_transport(client, handler)
    try:
        with pytest.raises(PaymentProviderError, match=r"invalid JSON"):
            await client.create_payment(
                local_id="00000000-0000-0000-0000-000000000003",
                amount=Decimal("100"),
                currency="RUB",
                description="ROX top-up",
                return_url="https://example.invalid/return",
            )
    finally:
        await client.aclose()
