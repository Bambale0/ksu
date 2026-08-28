from __future__ import annotations

import httpx
import pytest

from app.providers.card_checkout import CardCheckoutClient


@pytest.mark.asyncio
async def test_lava_product_lookup_includes_hidden_dynamic_price_products() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"items": []})

    client = CardCheckoutClient("api-key", "https://example.invalid")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(handler),
    )
    try:
        await client.get_products()
    finally:
        await client.aclose()

    assert len(seen) == 1
    assert seen[0].url.path == "/api/v2/products"
    assert seen[0].url.params.get("feedVisibility") == "ALL"
