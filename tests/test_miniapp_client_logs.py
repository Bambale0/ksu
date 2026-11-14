from app.api.v1 import client_logs
from app.api.v1.client_logs import _redact_client_text, _safe_pathname


def test_client_log_router_exposes_post_endpoint() -> None:
    assert any(
        getattr(route, "path", None) == "/client-logs"
        and "POST" in (getattr(route, "methods", None) or set())
        for route in client_logs.router.routes
    )


def test_safe_pathname_never_keeps_query_or_fragment() -> None:
    assert _safe_pathname(
        "/mini-app/?startapp=ref_777#tgWebAppData=query_id%3Dsecret"
    ) == "/mini-app/"


def test_client_log_redaction_removes_telegram_auth_material() -> None:
    raw = (
        "boom https://example.test/mini-app/?tgWebAppData=secret-payload "
        "query_id=q123&auth_date=1787760000&user=%7Bsecret%7D&hash=hash-secret "
        "X-Telegram-Init-Data=header-secret"
    )

    redacted = _redact_client_text(raw)

    for secret in (
        "secret-payload",
        "q123",
        "1787760000",
        "%7Bsecret%7D",
        "hash-secret",
        "header-secret",
    ):
        assert secret not in redacted
    assert "<redacted>" in redacted


def test_client_error_report_accepts_optional_build_id() -> None:
    report = client_logs.ClientErrorReport(
        kind="window_error",
        message="Script error.",
        build_id="abcdef123456",
    )
    assert report.build_id == "abcdef123456"
    legacy = client_logs.ClientErrorReport(
        kind="unhandled_rejection",
        message="Load failed",
    )
    assert legacy.build_id is None


def test_client_error_report_rejects_oversized_build_id() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        client_logs.ClientErrorReport(
            kind="window_error",
            message="Script error.",
            build_id="x" * 129,
        )
