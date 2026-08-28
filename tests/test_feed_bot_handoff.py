from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.bot.keyboards import feed_work_menu
from app.core.config import settings


ROOT = Path(__file__).resolve().parents[1]
START_HANDLER = ROOT / "app" / "bot" / "handlers" / "start.py"


def test_feed_work_button_opens_exact_publication_in_mini_app(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")
    payload = "feed_12345678-1234-5678-1234-567812345678_ref_777"

    markup = feed_work_menu(payload)
    button = markup.inline_keyboard[0][0]

    assert button.text == "Открыть работу в ROXY"
    assert button.web_app is not None
    parsed = urlparse(button.web_app.url)
    assert parsed.path == "/mini-app/"
    query = parse_qs(parsed.query)
    assert query["route"] == ["feed"]
    assert query["start_payload"] == [payload]
    assert query["startapp"] == [payload]


def test_feed_start_handoff_sends_work_then_exact_mini_app_button_without_quick_menu() -> None:
    source = START_HANDLER.read_text(encoding="utf-8")

    assert 'return bool(link is not None and link.action == "feed")' in source
    assert "if not feed_handoff:\n        await _send_quick_menu(message)" in source
    assert "if feed_handoff and payload:\n                await _send_feed_handoff_button(message, payload)" in source
    assert '"Открыть эту работу в ROXY 👇"' in source
    assert "reply_markup=feed_work_menu(payload)" in source
