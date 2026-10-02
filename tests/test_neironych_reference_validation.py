from __future__ import annotations

import json
import logging
from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

from app.core.config import settings
from app.core.logging import JsonFormatter
from app.services.media_probe import MediaProbe, _parse_probe
from app.services.neironych_reference_validation import (
    ReferenceValidationError,
    _inspect_url,
    inspect_file,
    owned_path,
    validate_reference_payload,
)


def test_actual_image_bytes_and_dimensions(tmp_path):
    valid = tmp_path / "actual.jpg"
    Image.new("RGB", (600, 600)).save(valid, format="JPEG")
    assert inspect_file("seedance-2.5", "image", valid) == 0
    Image.new("RGB", (200, 200)).save(valid, format="JPEG")
    with pytest.raises(ReferenceValidationError, match="300-6000"):
        inspect_file("seedance-2.5", "image", valid)
    assert inspect_file("seedance-2.0", "image", valid) == 0
    valid.write_bytes(b"not a JPEG despite extension")
    with pytest.raises(ReferenceValidationError):
        inspect_file("seedance-2.5", "image", valid)
    Image.new("RGB", (600, 600)).save(valid, format="WEBP")
    with pytest.raises(ReferenceValidationError, match="JPEG or PNG"):
        inspect_file("seedance-2.5", "image", valid)


@pytest.mark.parametrize(
    "change",
    [
        {"fps": 15},
        {"width": 200},
        {"duration_ms": 31000},
        {"container": "webm"},
        {"width": 320, "height": 320},
        {"fps": None},
    ],
)
def test_video_metadata_contract(tmp_path, monkeypatch, change):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"fixture")
    valid = MediaProbe(
        status="ready",
        duration_ms=5000,
        width=640,
        height=640,
        container="mov,mp4",
        video_codec="h264",
        fps=30,
    )
    monkeypatch.setattr(
        "app.services.neironych_reference_validation.probe_media_stream",
        lambda *args, **kwargs: valid,
    )
    assert inspect_file("seedance-2.5", "video", path) == 5
    invalid = replace(valid, **change)
    monkeypatch.setattr(
        "app.services.neironych_reference_validation.probe_media_stream",
        lambda *args, **kwargs: invalid,
    )
    with pytest.raises(ReferenceValidationError):
        inspect_file("seedance-2.5", "video", path)


def test_frame_rate_parser_handles_rational_and_invalid():
    assert _parse_probe(
        {"streams": [{"codec_type": "video", "avg_frame_rate": "30000/1001"}]}
    ).fps == pytest.approx(29.970, abs=0.001)
    assert _parse_probe({"streams": [{"codec_type": "video", "avg_frame_rate": "0/0"}]}).fps is None


@pytest.mark.asyncio
async def test_reference_aggregate_and_edit_source_limits(monkeypatch):
    inspector = AsyncMock(return_value=20.0)
    monkeypatch.setattr("app.services.neironych_reference_validation._inspect_url", inspector)
    with pytest.raises(ReferenceValidationError, match="total"):
        await validate_reference_payload(
            "seedance-2.5",
            {
                "reference_videos": [
                    {"url": "https://example.test/a"},
                    {"url": "https://example.test/b"},
                ]
            },
        )
    inspector.return_value = 3.0
    with pytest.raises(ReferenceValidationError, match="at least 4"):
        await validate_reference_payload(
            "seedance-2.5",
            {
                "omni_reference_task_type": "edit",
                "reference_videos": [{"url": "https://example.test/a"}],
            },
        )


def test_external_lookalike_is_not_a_trusted_local_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "public_base_url", "https://ksu.example")
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path))
    local = tmp_path / "a.png"
    Image.new("RGB", (600, 600)).save(local)
    assert owned_path("https://evil.example/uploads/refs/a.png") is None
    assert owned_path("https://ksu.example/uploads/refs/a.png") == local


@pytest.mark.asyncio
async def test_external_validation_preserves_signed_query_without_bearer(tmp_path, monkeypatch):
    path = tmp_path / "ref.png"
    Image.new("RGB", (600, 600)).save(path)
    checked = []

    async def validate(url):
        checked.append(url)

    monkeypatch.setattr(
        "app.services.neironych_reference_validation.MediaIngestService._validate_public_https_url",
        validate,
    )

    def handler(request):
        assert "authorization" not in request.headers
        assert request.url.query == b"signature=opaque-test-signature"
        return httpx.Response(200, content=path.read_bytes())

    url = "https://media.example/ref.png?signature=opaque-test-signature"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await _inspect_url(client, "seedance-2.5", "image", url) == 0
    assert checked == [url]


def test_structured_logs_redact_signed_urls_and_bearer():
    record = logging.LogRecord(
        "httpx",
        logging.INFO,
        "",
        1,
        "GET https://storage.example/a?signature=private-signature Authorization: Bearer private-token",
        (),
        None,
    )
    rendered = json.loads(JsonFormatter().format(record))["message"]
    assert "private-signature" not in rendered and "private-token" not in rendered
    assert "storage.example/a" in rendered
