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

@pytest.mark.asyncio
async def test_seedance_existing_mpo_jpeg_uses_stable_normalized_provider_image(
    tmp_path, monkeypatch,
):
    """A legacy .jpg containing an MPO must work without changing trend references."""
    import uuid
    from types import SimpleNamespace
    from app.providers.neironych_submission import SNAPSHOT_KEY
    from app.services.neironych_generation_provider import NeironychGenerationProviderService
    from app.services.reference_static import ReferenceStaticStorage

    root = tmp_path / "refs"
    root.mkdir()
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setattr(settings, "public_base_url", "https://ksu.example")

    original = root / "legacy.jpg"
    Image.new("RGB", (600, 600), (48, 84, 120)).save(original, format="JPEG")
    original_bytes = original.read_bytes()
    legacy_url = ReferenceStaticStorage.public_url("legacy.jpg")
    other = root / "regular.jpg"
    Image.new("RGB", (600, 600), (11, 22, 33)).save(other, format="JPEG")
    other_url = ReferenceStaticStorage.public_url("regular.jpg")

    # An MPO is a JPEG-based image with MPF metadata; Pillow reports its
    # format as MPO even when a storage client declared image/jpeg.
    real_open = Image.open

    def open_mpo_fixture(path, *args, **kwargs):
        image = real_open(path, *args, **kwargs)
        if str(path) == str(original):
            image.format = "MPO"
        return image

    monkeypatch.setattr(
        "app.services.neironych_reference_validation.Image.open", open_mpo_fixture
    )

    def generation():
        return SimpleNamespace(
            id=uuid.uuid4(),
            input_url=None,
            action_type="generate",
            prompt="Animate the photograph",
            parameters={
                "_model_id": "seedance-2.5",
                "reference_image_urls": [legacy_url, other_url],
                "duration": 6,
                "resolution": "480p",
                "aspect_ratio": "16:9",
            },
        )

    first = generation()
    await NeironychGenerationProviderService._freeze_new_submission(None, first)
    body = json.loads(first.parameters[SNAPSHOT_KEY]["body_json"])
    converted_url = body["reference_images"][0]["url"]
    assert body["reference_images"][1]["url"] == other_url
    assert converted_url != legacy_url
    assert converted_url.startswith("https://ksu.example/uploads/refs/normalized/")
    target = ReferenceStaticStorage.path_for_url(converted_url)
    assert target is not None and target.is_file()
    with real_open(target) as converted:
        assert converted.format == "JPEG" and converted.size == (600, 600)
    assert original.read_bytes() == original_bytes
    assert first.parameters["reference_image_urls"] == [legacy_url, other_url]

    second = generation()
    await NeironychGenerationProviderService._freeze_new_submission(None, second)
    assert json.loads(second.parameters[SNAPSHOT_KEY]["body_json"])["reference_images"][0]["url"] == converted_url
    assert len(list(root.rglob("*.jpg"))) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("dimensions", [(6001, 4000), (6000, 2000), (299, 600)])
async def test_oversize_mpo_rejected_before_first_frame_decode(
    tmp_path, monkeypatch, dimensions,
):
    """A misleadingly small compressed MPO cannot trigger a huge RGB decode."""
    import uuid
    from types import SimpleNamespace

    from app.services.neironych_generation_provider import NeironychGenerationProviderService
    from app.services.reference_static import ReferenceStaticStorage

    root = tmp_path / "refs"
    root.mkdir()
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setattr(settings, "public_base_url", "https://ksu.example")
    original = root / "oversize.jpg"
    Image.new("RGB", (600, 600)).save(original, "JPEG")

    real_open = Image.open

    def misleading_mpo(path, *args, **kwargs):
        source = real_open(path, *args, **kwargs)
        if str(path) == str(original):
            source.format = "MPO"
            source._size = dimensions
        return source

    monkeypatch.setattr(
        "app.services.neironych_reference_validation.Image.open", misleading_mpo
    )

    def no_decode(*_args, **_kwargs):
        pytest.fail("Invalid MPO must be rejected before image frame decoding")

    monkeypatch.setattr(
        "app.services.neironych_reference_validation.ImageOps.exif_transpose",
        no_decode,
    )
    row = SimpleNamespace(
        id=uuid.uuid4(),
        input_url=None,
        action_type="generate",
        prompt="Test",
        parameters={
            "_model_id": "seedance-2.5",
            "reference_image_urls": [ReferenceStaticStorage.public_url("oversize.jpg")],
            "duration": 6,
            "resolution": "480p",
            "aspect_ratio": "16:9",
        },
    )
    with pytest.raises(ReferenceValidationError, match="300-6000"):
        await NeironychGenerationProviderService._freeze_new_submission(None, row)
    assert not (root / "normalized").exists()


@pytest.mark.asyncio
async def test_seedance_normal_jpeg_remains_original_provider_url(tmp_path, monkeypatch):
    from app.services.neironych_generation_provider import NeironychGenerationProviderService
    from app.services.reference_static import ReferenceStaticStorage
    from types import SimpleNamespace
    import uuid

    root = tmp_path / "refs"
    root.mkdir()
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setattr(settings, "public_base_url", "https://ksu.example")
    original = root / "normal.jpg"
    Image.new("RGB", (600, 600), (1, 2, 3)).save(original, format="JPEG")
    url = ReferenceStaticStorage.public_url("normal.jpg")
    generation = SimpleNamespace(
        id=uuid.uuid4(),
        input_url=None,
        action_type="generate",
        prompt="Animate the photograph",
        parameters={
            "_model_id": "seedance-2.5", "reference_image_urls": [url],
            "duration": 6, "resolution": "480p", "aspect_ratio": "16:9",
        },
    )
    await NeironychGenerationProviderService._freeze_new_submission(None, generation)
    from app.providers.neironych_submission import SNAPSHOT_KEY
    assert json.loads(generation.parameters[SNAPSHOT_KEY]["body_json"])["reference_images"][0]["url"] == url
    assert len(list(root.rglob("*.jpg"))) == 1
