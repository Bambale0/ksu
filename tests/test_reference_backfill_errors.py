import importlib.util
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


def test_reference_backfill_classifies_expired_provider_urls_as_unavailable() -> None:
    request = httpx.Request("GET", "https://tempfile.example.invalid/old.jpg")
    response = httpx.Response(404, request=request)

    assert backfill_reference_static._is_unavailable_source(
        httpx.HTTPStatusError("missing", request=request, response=response)
    )
    assert backfill_reference_static._is_unavailable_source(
        httpx.ConnectError("dns failed", request=request)
    )
