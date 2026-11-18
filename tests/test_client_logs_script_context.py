"""Mini App error telemetry never admits raw URLs or Telegram auth data."""

from app.api.v1.client_logs import ClientErrorReport, _safe_script_file


def test_script_file_keeps_only_bounded_js_basenames() -> None:
    assert _safe_script_file("main-a1b2c3.js") == "main-a1b2c3.js"
    assert _safe_script_file("chunk.mjs") == "chunk.mjs"
    assert _safe_script_file("https://cdn.example/mini-app/chunk.js?initData=secret") == ""
    assert _safe_script_file("../chunk.js") == ""
    assert _safe_script_file("chunk.js?hash=secret") == ""
    assert _safe_script_file("chunk.png") == ""
    assert _safe_script_file(None) == ""


def test_report_accepts_bounded_script_location() -> None:
    report = ClientErrorReport(
        kind="window_error",
        message="Script error.",
        script_file="main.js",
        script_line=123,
        script_column=5,
    )
    assert report.script_file == "main.js"
    assert report.script_line == 123
    assert report.script_column == 5
