from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.providers.kie import KieProviderError


@dataclass(frozen=True, slots=True)
class KieCreditBalance:
    credits: Decimal


class KieCreditClient:
    """Small Kie Common API client dedicated to account-credit monitoring."""

    def __init__(self, api_key: str, base_url: str = "https://api.kie.ai") -> None:
        if not api_key:
            raise KieProviderError("KIE_API_KEY is not configured")
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_remaining_credits(self) -> KieCreditBalance:
        try:
            response = await self._client.get("/api/v1/chat/credit")
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise KieProviderError("Kie credit balance request failed") from exc

        raw_code = payload.get("code")
        try:
            code = int(raw_code)
        except (TypeError, ValueError) as exc:
            raise KieProviderError(f"Kie credit balance returned invalid code: {payload!r}") from exc
        if code != 200:
            message = payload.get("msg") or payload.get("message") or payload
            raise KieProviderError(f"Kie credit balance rejected: {message!r}")

        raw_credits = payload.get("data")
        if isinstance(raw_credits, bool):
            raise KieProviderError(f"Kie credit balance returned invalid balance: {payload!r}")
        try:
            credits = Decimal(str(raw_credits))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise KieProviderError(f"Kie credit balance returned invalid balance: {payload!r}") from exc
        if not credits.is_finite() or credits < 0:
            raise KieProviderError(f"Kie credit balance returned invalid balance: {payload!r}")
        return KieCreditBalance(credits=credits)
