from app.api.router import api_router
from app.api.v1.client_logs import _redact_client_text, _safe_pathname


def test_client_log_route_is_registered() -> None:
    assert any(
        route.path == "/api/v1/client-logs" and "POST" in (route.methods or set())
        for route in api_router.routes
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
