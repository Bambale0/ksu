from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import PaymentProviderValidationError
from app.services.card_payments import CardPackage, CardPackageCatalog


CONFIGURED_OFFER_ID = "11111111-2222-4333-8444-555555555555"


@pytest.mark.asyncio
async def test_dynamic_checkout_posts_resolved_offer_id_verbatim() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET" and request.url.path == "/api/v2/products":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "parent-content-id",
                            "offers": [
                                {
                                    "id": CONFIGURED_OFFER_ID,
                                    "isPriceOnRequestViaAPI": True,
                                }
                            ],
                        }
                    ]
                },
            )
        if request.method == "POST" and request.url.path == "/api/v3/invoice":
            payload = json.loads(request.content.decode("utf-8"))
            if payload.get("offerId") != CONFIGURED_OFFER_ID:
                return httpx.Response(
                    404,
                    json={"message": "configured Lava offer id was rewritten"},
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
        offer_id=CONFIGURED_OFFER_ID,
        dynamic_amount=True,
    )

    try:
        resolution = await CardPackageCatalog.resolve_invoice_offer(client, package)
        assert resolution.offer_id == CONFIGURED_OFFER_ID

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
    assert "feedVisibility" not in seen[0].url.params
    payload = json.loads(seen[1].content.decode("utf-8"))
    assert payload == {
        "email": "buyer@example.com",
        "offerId": CONFIGURED_OFFER_ID,
        "currency": "RUB",
        "amount": 300.0,
    }


@pytest.mark.asyncio
async def test_dynamic_checkout_keeps_configured_id_when_catalog_hides_product() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET" and request.url.path == "/api/v2/products":
            return httpx.Response(200, json={"items": []})
        if request.method == "POST" and request.url.path == "/api/v3/invoice":
            payload = json.loads(request.content.decode("utf-8"))
            if payload.get("offerId") != CONFIGURED_OFFER_ID:
                return httpx.Response(400, json={"message": "wrong offerId"})
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
    package = CardPackage(
        package_id="starter",
        credits=Decimal("300"),
        prices={"RUB": Decimal("300")},
        offer_id=CONFIGURED_OFFER_ID,
        dynamic_amount=True,
    )

    try:
        resolution = await CardPackageCatalog.resolve_invoice_offer(client, package)
        assert resolution.offer_id == CONFIGURED_OFFER_ID
        assert resolution.source == "configured"

        created = await client.create_invoice(
            email="buyer@example.com",
            offer_id=resolution.offer_id,
            currency="RUB",
            amount=Decimal("300"),
        )
    finally:
        await client.aclose()

    assert created.external_id == "contract-456"
    payload = json.loads(seen[1].content.decode("utf-8"))
    assert payload["offerId"] == CONFIGURED_OFFER_ID


@pytest.mark.asyncio
async def test_lava_incorrect_email_is_user_validation_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v3/invoice":
            return httpx.Response(
                400,
                json={
                    "error": "Incorrect email to purchase",
                    "details": {},
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
        with pytest.raises(PaymentProviderValidationError, match="другой email"):
            await client.create_invoice(
                email="buyer@mail.ru",
                offer_id=CONFIGURED_OFFER_ID,
                currency="RUB",
                amount=Decimal("300"),
            )
    finally:
        await client.aclose()
