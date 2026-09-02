import importlib.util
import socket
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "backfill_reference_static",
    ROOT / "scripts" / "backfill_reference_static.py",
)
assert SPEC is not None and SPEC.loader is not None
backfill_reference_static = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = backfill_reference_static
SPEC.loader.exec_module(backfill_reference_static)


def test_reference_backfill_only_classifies_terminal_http_sources_as_unavailable() -> None:
    request = httpx.Request("GET", "https://tempfile.example.invalid/old.jpg")

    for status in (404, 410):
        response = httpx.Response(status, request=request)
        assert backfill_reference_static._is_unavailable_source(
            httpx.HTTPStatusError("missing", request=request, response=response)
        )

    response = httpx.Response(503, request=request)
    assert not backfill_reference_static._is_unavailable_source(
        httpx.HTTPStatusError("temporary", request=request, response=response)
    )
    assert not backfill_reference_static._is_unavailable_source(
        httpx.ConnectError("dns failed", request=request)
    )


def test_reference_backfill_marks_network_errors_as_transient_failures() -> None:
    request = httpx.Request("GET", "https://tempfile.example.invalid/old.jpg")

    for error in (
        httpx.ConnectError("connect failed", request=request),
        httpx.ConnectTimeout("connect timeout", request=request),
        httpx.ReadTimeout("read timeout", request=request),
        httpx.RemoteProtocolError("protocol reset", request=request),
        socket.gaierror(socket.EAI_AGAIN, "temporary name resolution failure"),
        TimeoutError("temporary timeout"),
    ):
        assert backfill_reference_static._is_transient_source_error(error)
