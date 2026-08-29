from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


DEFAULT_LOG_FILE = Path("logs/bot.log")
DEFAULT_ERROR_LOG_FILE = Path("logs/errors.log")
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5
SAFE_EXTRA_FIELDS = ("http_method", "http_route", "http_status", "duration_ms")


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
        for field in SAFE_EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class ErrorLogFilter(logging.Filter):
    """Route only actionable failures into the dedicated error log."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR:
            return True
        status = getattr(record, "http_status", None)
        try:
            return int(status) >= 500
        except (TypeError, ValueError):
            return False


def _stream_handler(formatter: logging.Formatter) -> logging.Handler:
    handler = logging.StreamHandler()
    handler.addFilter(ObservabilityFilter())
    handler.setFormatter(formatter)
    return handler


def configure_logging(
    log_file: str | Path = DEFAULT_LOG_FILE,
    *,
    error_log_file: str | Path | None = DEFAULT_ERROR_LOG_FILE,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> None:
    """Configure structured stdout logs plus rotating application log files."""

    from app.core.config import settings

    root = logging.getLogger()
    level = getattr(logging, str(settings.log_level).upper(), logging.INFO)
    root.setLevel(level)

    formatter = JsonFormatter()
    stream_handler = _stream_handler(formatter)

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max(1, int(max_bytes)),
        backupCount=max(1, int(backup_count)),
        encoding="utf-8",
        delay=True,
    )
    file_handler.addFilter(ObservabilityFilter())
    file_handler.setFormatter(formatter)

    previous_handlers = list(root.handlers)
    root.handlers.clear()
    for handler in previous_handlers:
        try:
            handler.close()
        except Exception:
            pass

    root.addHandler(stream_handler)
    root.addHandler(file_handler)
    if error_log_file is not None:
        error_log_path = Path(error_log_file)
        error_log_path.parent.mkdir(parents=True, exist_ok=True)
        error_file_handler = RotatingFileHandler(
            error_log_path,
            maxBytes=max(1, int(max_bytes)),
            backupCount=max(1, int(backup_count)),
            encoding="utf-8",
            delay=True,
        )
        error_file_handler.addFilter(ObservabilityFilter())
        error_file_handler.addFilter(ErrorLogFilter())
        error_file_handler.setFormatter(formatter)
        root.addHandler(error_file_handler)
