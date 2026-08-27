from __future__ import annotations

import logging
import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/client-logs", tags=["client-logs"])


ClientErrorKind = Literal[
    "window_error",
    "unhandled_rejection",
    "react_error",
]


class ClientErrorReport(BaseModel):
    kind: ClientErrorKind
    message: str = Field(min_length=1, max_length=1000)
    stack: str | None = Field(default=None, max_length=6000)
    component_stack: str | None = Field(default=None, max_length=6000)
    pathname: str = Field(default="/mini-app/", max_length=256)
    user_agent: str = Field(default="", max_length=512)
    platform: str = Field(default="", max_length=64)
    viewport_width: int | None = Field(default=None, ge=0, le=10000)
    viewport_height: int | None = Field(default=None, ge=0, le=10000)
    device_pixel_ratio: float | None = Field(default=None, ge=0, le=20)
    digest: str | None = Field(default=None, max_length=256)


_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(tgWebAppData|x-telegram-init-data|initData)\s*[:=]\s*([^\s\"']+)"
)
_TELEGRAM_INIT_FIELD_RE = re.compile(
    r"(?i)(^|[?&#\s])(query_id|auth_date|hash|signature|user)=([^&#\s]+)"
)


def _safe_pathname(value: str) -> str:
    """Keep only the path; Telegram auth/start payloads must never enter logs."""

    path = str(value or "/mini-app/").split("?", 1)[0].split("#", 1)[0].strip()
    if not path.startswith("/"):
        path = f"/{path}"
    return path[:256] or "/mini-app/"


def _redact_client_text(value: str | None) -> str:
    """Remove Telegram auth material from untrusted browser diagnostics."""

    text = str(value or "")
    text = _SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    text = _TELEGRAM_INIT_FIELD_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}=<redacted>",
        text,
    )
    return text


@router.post("")
async def record_client_error(
    payload: ClientErrorReport,
    user: CurrentUserDep,
) -> dict[str, bool]:
    """Record bounded, authenticated Mini App diagnostics without auth payloads."""

    pathname = _safe_pathname(payload.pathname)
    logger.error(
        "miniapp_client_error kind=%s user_id=%s telegram_id=%s path=%s "
        "platform=%s viewport=%sx%s dpr=%s digest=%s message=%r stack=%r component_stack=%r ua=%r",
        payload.kind,
        user.id,
        user.telegram_id,
        pathname,
        payload.platform,
        payload.viewport_width,
        payload.viewport_height,
        payload.device_pixel_ratio,
        payload.digest or "",
        _redact_client_text(payload.message),
        _redact_client_text(payload.stack),
        _redact_client_text(payload.component_stack),
        payload.user_agent,
    )
    return {"accepted": True}
