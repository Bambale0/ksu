from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.db.session import SessionFactory
from app.services.admin_pricing import AdminPricingService


# These are the customer-facing boundaries where stale pricing is unacceptable:
# generation pricing plus payment catalogs and checkout creation must always use
# the latest published admin tariff.
_PRICE_SENSITIVE_REQUESTS = frozenset(
    {
        ("GET", "/api/v1/generations/models"),
        ("POST", "/api/v1/generations/quote"),
        ("POST", "/api/v1/generations"),
        ("GET", "/api/v1/payments/packages"),
        ("GET", "/api/v1/payments/yookassa/packages"),
        ("GET", "/api/v1/payments/card/packages"),
        ("GET", "/api/v1/payments/crypto/packages"),
        ("GET", "/api/v1/payments/crypto/2328/packages"),
        ("POST", "/api/v1/payments"),
        ("POST", "/api/v1/payments/card/checkout"),
        ("POST", "/api/v1/payments/crypto/checkout"),
        ("POST", "/api/v1/payments/crypto/2328/checkout"),
    }
)


class PricingRuntimeSyncMiddleware:
    """Synchronize the current worker with the published PostgreSQL tariff.

    Admin tariff publication can be handled by a different process. Reading
    the published version at price-sensitive boundaries guarantees that generation
    quotes/debits and payment catalogs/checkouts use the same tariff without a
    process restart.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and settings.app_env.lower() != "test":
            method = str(scope.get("method") or "GET").upper()
            path = str(scope.get("path") or "")
            if (method, path) in _PRICE_SENSITIVE_REQUESTS:
                async with SessionFactory() as session:
                    await AdminPricingService.hydrate_runtime(session)
        await self.app(scope, receive, send)
