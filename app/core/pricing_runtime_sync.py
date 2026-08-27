from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.db.session import SessionFactory
from app.services.admin_pricing import AdminPricingService


# These are the customer-facing boundaries where stale pricing is unacceptable:
# the model picker, quote calculation and the actual generation create request.
_PRICE_SENSITIVE_REQUESTS = frozenset(
    {
        ("GET", "/api/v1/generations/models"),
        ("POST", "/api/v1/generations/quote"),
        ("POST", "/api/v1/generations"),
    }
)


class PricingRuntimeSyncMiddleware:
    """Synchronize the current worker with the published PostgreSQL tariff.

    Admin tariff publication can be handled by a different API worker. Reading
    the published version at price-sensitive boundaries guarantees that catalog,
    quote and debit use the same tariff without requiring a process restart.
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
