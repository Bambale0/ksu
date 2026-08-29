from __future__ import annotations

import logging
import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.observability import HTTP_DURATION, HTTP_REQUESTS, request_id_var

logger = logging.getLogger("ksu.http")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_RE.fullmatch(incoming) else str(uuid.uuid4())
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration = max(0.0, time.perf_counter() - started)
            route = request.scope.get("route")
            route_template = str(getattr(route, "path", "__unmatched__"))
            method = request.method.upper()
            HTTP_REQUESTS.labels(
                method=method,
                route=route_template,
                status=str(status_code),
            ).inc()
            HTTP_DURATION.labels(method=method, route=route_template).observe(duration)
            log = logger.error if status_code >= 500 else logger.info
            log(
                "http_request method=%s route=%s status=%s duration_ms=%.3f",
                method,
                route_template,
                status_code,
                duration * 1000,
                extra={
                    "http_method": method,
                    "http_route": route_template,
                    "http_status": status_code,
                    "duration_ms": round(duration * 1000, 3),
                },
            )
            request_id_var.reset(token)
