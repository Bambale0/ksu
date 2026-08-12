from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.core.config import settings
from app.db.session import SessionFactory
from app.services.abuse_protection import ResourcePolicyError
from app.core.observability import RESOURCE_POLICY_EVENTS, refresh_snapshot_metrics

router = APIRouter(tags=["metrics"])


def _authorize(authorization: str | None) -> None:
    expected = settings.metrics_bearer_token
    if not expected:
        return
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid metrics authorization")


@router.get("/metrics", include_in_schema=False)
async def metrics(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Metrics are disabled")
    _authorize(authorization)
    try:
        async with SessionFactory() as session:
            await refresh_snapshot_metrics(session, request.app.state.redis)
    except ResourcePolicyError as exc:
        RESOURCE_POLICY_EVENTS.labels(code=exc.code).inc()
        raise
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
