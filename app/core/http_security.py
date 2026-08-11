from __future__ import annotations

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object) -> Response:
        incoming_id = request.headers.get("x-request-id", "")
        request_id = incoming_id if REQUEST_ID_RE.fullmatch(incoming_id) else uuid.uuid4().hex
        request.state.request_id = request_id

        response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-Frame-Options"] = "DENY"

        if request.url.path.startswith("/api/v1/admin"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"

        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
