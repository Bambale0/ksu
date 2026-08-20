from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.logging import DEFAULT_LOG_FILE, configure_logging


def test_default_bot_log_path_is_stable() -> None:
    assert DEFAULT_LOG_FILE == Path("logs/bot.log")


def test_configure_logging_writes_structured_file(tmp_path: Path) -> None:
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    log_file = tmp_path / "logs" / "bot.log"

    try:
        configure_logging(log_file, max_bytes=1024, backup_count=2)
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
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
        for handler in previous_handlers:
            root.addHandler(handler)
        root.setLevel(previous_level)
