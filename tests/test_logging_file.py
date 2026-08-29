from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.logging import (
    DEFAULT_ERROR_LOG_FILE,
    DEFAULT_LOG_FILE,
    ErrorLogFilter,
    configure_logging,
)


def test_default_bot_log_path_is_stable() -> None:
    assert DEFAULT_LOG_FILE == Path("logs/bot.log")
    assert DEFAULT_ERROR_LOG_FILE == Path("logs/errors.log")


def _restore_logging(root: logging.Logger, handlers: list[logging.Handler], level: int) -> None:
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)


def test_configure_logging_writes_structured_file(tmp_path: Path) -> None:
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    log_file = tmp_path / "logs" / "bot.log"

    try:
        configure_logging(
            log_file,
            error_log_file=tmp_path / "logs" / "errors.log",
            max_bytes=1024,
            backup_count=2,
        )
        logging.getLogger("tests.bot-log").info("bot log smoke")
        for handler in root.handlers:
            handler.flush()

        assert log_file.exists()
        payload = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert payload["level"] == "INFO"
        assert payload["logger"] == "tests.bot-log"
        assert payload["message"] == "bot log smoke"
        assert "request_id" in payload
        assert "trace_id" in payload
        assert "span_id" in payload
    finally:
        _restore_logging(root, previous_handlers, previous_level)


def test_configure_logging_writes_only_failures_to_error_file(tmp_path: Path) -> None:
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    log_file = tmp_path / "logs" / "bot.log"
    error_log_file = tmp_path / "logs" / "errors.log"

    try:
        configure_logging(
            log_file,
            error_log_file=error_log_file,
            max_bytes=1024,
            backup_count=2,
        )
        logger = logging.getLogger("tests.error-log")
        logger.info("regular log")
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.exception("critical path failed")
        for handler in root.handlers:
            handler.flush()

        lines = error_log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["level"] == "ERROR"
        assert payload["message"] == "critical path failed"
        assert "RuntimeError: boom" in payload["exception"]
    finally:
        _restore_logging(root, previous_handlers, previous_level)


def test_error_log_filter_accepts_http_5xx_records() -> None:
    record = logging.LogRecord(
        name="ksu.http",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="http_request method=GET route=/boom status=503 duration_ms=1.000",
        args=(),
        exc_info=None,
    )
    record.http_status = 503
    assert ErrorLogFilter().filter(record) is True

    record.http_status = 499
    assert ErrorLogFilter().filter(record) is False
