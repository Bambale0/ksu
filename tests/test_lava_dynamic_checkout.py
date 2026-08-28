from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from app.providers.card_checkout import CardCheckoutClient
from app.services.card_payments import CardPackage, CardPackageCatalog


@pytest.mark.asyncio
async def test_dynamic_price_checkout_keeps_configured_content_id() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET" and request.url.path == "/api/v2/products":
            # Lava hides API-request-price products from the default catalog.
            return httpx.Response(200, json={"items": []})
        if request.method == "POST" and request.url.path == "/api/v3/invoice":
            return httpx.Response(
                200,
                json={
                    "id": "contract-123",
                    "paymentUrl": "https://pay.example.invalid/contract-123",
                },
            )
        return httpx.Response(404)

    client = CardCheckoutClient("api-key", "https://example.invalid")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(handler),
    )
    package = CardPackage(
        package_id="starter",
        credits=Decimal("300"),
        prices={"RUB": Decimal("300")},
        offer_id="content-product-id",
        dynamic_amount=True,
    )

    try:
        resolution = await CardPackageCatalog.resolve_invoice_offer(client, package)
        created = await client.create_invoice(
            email="buyer@example.com",
            offer_id=resolution.offer_id,
            currency="RUB",
            amount=Decimal("300"),
        )
    finally:
        await client.aclose()

    assert resolution.offer_id == "content-product-id"
    assert resolution.source == "configured"
    assert created.external_id == "contract-123"
    assert created.payment_url == "https://pay.example.invalid/contract-123"

    assert [request.url.path for request in seen] == [
        "/api/v2/products",
        "/api/v3/invoice",
    ]
    assert "feedVisibility" not in seen[0].url.params
    payload = json.loads(seen[1].content.decode("utf-8"))
    assert payload == {
        "email": "buyer@example.com",
        "offerId": "content-product-id",
        "currency": "RUB",
        "amount": 300.0,
    }
