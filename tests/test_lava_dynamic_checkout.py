from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from app.providers.card_checkout import CardCheckoutClient
from app.services.card_payments import CardPackage, CardPackageCatalog


@pytest.mark.asyncio
async def test_dynamic_price_checkout_posts_content_id_for_real_hidden_product() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET" and request.url.path == "/api/v2/products":
            # This mirrors the production case that PR #308 failed to cover:
            # the hidden product is present and has a nested offer with another id.
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "content-product-id",
                            "offers": [
                                {
                                    "id": "nested-offer-id",
                                    "isPriceOnRequestViaAPI": True,
                                }
                            ],
                        }
                    ]
                },
            )
        if request.method == "POST" and request.url.path == "/api/v3/invoice":
            payload = json.loads(request.content.decode("utf-8"))
            if payload.get("offerId") != "content-product-id":
                return httpx.Response(
                    400,
                    json={"message": "dynamic invoice requires content id"},
                )
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
        # The legacy service resolver still sees the nested offer. The provider
        # boundary must normalize it back to the content id required by Lava v3.
        resolution = await CardPackageCatalog.resolve_invoice_offer(client, package)
        assert resolution.offer_id == "nested-offer-id"

        created = await client.create_invoice(
            email="buyer@example.com",
            offer_id=resolution.offer_id,
            currency="RUB",
            amount=Decimal("300"),
        )
    finally:
        await client.aclose()

    assert created.external_id == "contract-123"
    assert created.payment_url == "https://pay.example.invalid/contract-123"

    assert [request.url.path for request in seen] == [
        "/api/v2/products",
        "/api/v3/invoice",
    ]
    assert seen[0].url.params.get("feedVisibility") == "ALL"
    payload = json.loads(seen[1].content.decode("utf-8"))
    assert payload == {
        "email": "buyer@example.com",
        "offerId": "content-product-id",
        "currency": "RUB",
        "amount": 300.0,
    }


@pytest.mark.asyncio
async def test_dynamic_price_checkout_keeps_configured_content_id() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET" and request.url.path == "/api/v2/products":
            return httpx.Response(
                200,
                json={"items": [{"id": "content-product-id", "offers": []}]},
            )
        if request.method == "POST" and request.url.path == "/api/v3/invoice":
            return httpx.Response(
                200,
                json={
                    "id": "contract-456",
                    "paymentUrl": "https://pay.example.invalid/contract-456",
                },
            )
        return httpx.Response(404)

    client = CardCheckoutClient("api-key", "https://example.invalid")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(handler),
    )

    try:
        created = await client.create_invoice(
            email="buyer@example.com",
            offer_id="content-product-id",
            currency="RUB",
            amount=Decimal("300"),
        )
    finally:
        await client.aclose()

    assert created.external_id == "contract-456"
    assert [request.url.path for request in seen] == [
        "/api/v2/products",
        "/api/v3/invoice",
    ]
    payload = json.loads(seen[1].content.decode("utf-8"))
    assert payload["offerId"] == "content-product-id"
