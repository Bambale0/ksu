"""Lightweight structured telemetry for the generation action platform.

Events are emitted through the standard logger (OTel/log collectors already
aggregate it). Event names are part of the analytics contract — do not rename
without updating dashboards.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("roxy.action_telemetry")

GENERATION_ACTION_CLICKED = "generation_action_clicked"
ACTION_CONTEXT_CREATED = "action_context_created"
ACTION_CONTEXT_OPENED = "action_context_opened"
ACTION_EXECUTED = "action_executed"
PUBLISH_SUCCESS = "publish_success"
SHARE_CLICKED = "share_clicked"


def track(event: str, *, user_id: Any = None, **fields: Any) -> None:
    payload: dict[str, Any] = {"event": event}
    if user_id is not None:
        payload["user_id"] = str(user_id)
    for key, value in fields.items():
        if value is not None:
            payload[key] = str(value) if not isinstance(value, (int, float, bool)) else value
    logger.info("action_telemetry %s", event, extra={"action_telemetry": payload})
