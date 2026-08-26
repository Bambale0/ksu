from __future__ import annotations

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object) -> Response:
        incoming_id = request.headers.get("x-request-id", "")
        request_id = incoming_id if REQUEST_ID_RE.fullmatch(incoming_id) else uuid.uuid4().hex
        request.state.request_id = request_id

        # Security-sensitive production endpoints fail closed when their bearer
        # secret was omitted from deployment configuration. Development/test can
        # stay lightweight without teaching production to accept unsigned input.
        path = request.url.path
        if settings.is_production:
            if path == "/webhooks/telegram" and not settings.telegram_webhook_secret:
                response = JSONResponse(
                    status_code=503,
                    content={"detail": "Telegram webhook security is not configured"},
                )
                return self._secure_response(response, request_id, path)
            if path == "/metrics" and settings.metrics_enabled and not settings.metrics_bearer_token:
                response = JSONResponse(
                    status_code=503,
                    content={"detail": "Metrics authorization is not configured"},
                )
                return self._secure_response(response, request_id, path)

        response = await call_next(request)  # type: ignore[operator]
        return self._secure_response(response, request_id, path)

    @staticmethod
    def _secure_response(response: Response, request_id: str, path: str) -> Response:
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-Frame-Options"] = "DENY"

        if path == "/mini-app" or path.startswith("/mini-app/"):
            # Telegram WebView can retain HTML/JS/CSS aggressively between launches.
            # Mini App assets are small and release-sensitive, so freshness wins over
            # browser caching here. Provider/generated media is served elsewhere.
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        if path.startswith("/api/v1/admin"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"

        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
