from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


class ObservabilityFilter(logging.Filter):
    """Attach correlation fields without making logging depend on request plumbing."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from app.core.observability import current_trace_fields, request_id_var

            record.request_id = request_id_var.get() or ""
            trace_fields = current_trace_fields()
            record.trace_id = trace_fields["trace_id"]
            record.span_id = trace_fields["span_id"]
        except Exception:
            # Logging must remain available even if optional telemetry initialization fails.
            record.request_id = getattr(record, "request_id", "")
            record.trace_id = getattr(record, "trace_id", "")
            record.span_id = getattr(record, "span_id", "")
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": str(getattr(record, "request_id", "") or ""),
            "trace_id": str(getattr(record, "trace_id", "") or ""),
            "span_id": str(getattr(record, "span_id", "") or ""),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.addFilter(ObservabilityFilter())
    handler.setFormatter(JsonFormatter())

    root.handlers.clear()
    root.addHandler(handler)
