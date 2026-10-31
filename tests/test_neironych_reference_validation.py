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
    ReferenceValidationUnavailable,
    _inspect_url,
    inspect_file,
    normalize_seedance_image_references,
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


@pytest.mark.asyncio
async def test_normalized_images_are_not_downloaded_twice(monkeypatch):
    inspector = AsyncMock()
    monkeypatch.setattr("app.services.neironych_reference_validation._inspect_url", inspector)
    url = "https://media.example/already-byte-checked.jpg"

    await validate_reference_payload(
        "seedance-2.5",
        {"reference_images": [{"url": url}]},
        validated_image_urls={url},
    )

    inspector.assert_not_awaited()


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


@pytest.mark.asyncio
async def test_external_webp_download_is_bounded_and_normalized_without_credentials(
    tmp_path, monkeypatch,
):
    import io

    from app.services.neironych_reference_validation import _normalize_image_url
    from app.services.reference_static import ReferenceStaticStorage

    root = tmp_path / "refs"
    root.mkdir()
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setattr(settings, "public_base_url", "https://ksu.example")
    checked: list[str] = []

    async def validate(url: str) -> None:
        checked.append(url)

    monkeypatch.setattr(
        "app.services.neironych_reference_validation.MediaIngestService._validate_public_https_url",
        validate,
    )
    source = io.BytesIO()
    Image.new("RGB", (600, 800), (23, 45, 67)).save(source, format="WEBP")
    content = source.getvalue()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.query == b"signature=opaque"
        assert "authorization" not in request.headers
        return httpx.Response(
            200,
            content=content,
            headers={"content-length": str(len(content)), "content-type": "image/jpeg"},
        )

    url = "https://media.example/photo.jpg?signature=opaque"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        normalized_url = await _normalize_image_url(client, "seedance-2.5", url)

    assert normalized_url != url
    assert normalized_url.startswith("https://ksu.example/uploads/refs/normalized/")
    target = ReferenceStaticStorage.path_for_url(normalized_url)
    assert target is not None and target.is_file()
    with Image.open(target) as image:
        assert image.format == "JPEG"
        assert image.size == (600, 800)
        image.verify()
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
@pytest.mark.parametrize(
    "model,dimensions,error",
    [
        ("seedance-2.5", (6001, 4000), "300-6000"),
        ("seedance-2.5", (6000, 2000), "300-6000"),
        ("seedance-2.5", (299, 600), "300-6000"),
        ("seedance-2.0", (9000, 5000), "safe normalization"),
    ],
)
async def test_oversize_mpo_rejected_before_first_frame_decode(
    tmp_path, monkeypatch, model, dimensions, error,
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
            "_model_id": model,
            "reference_image_urls": [ReferenceStaticStorage.public_url("oversize.jpg")],
            "duration": 6,
            "resolution": "480p",
            "aspect_ratio": "16:9",
        },
    )
    with pytest.raises(ReferenceValidationError, match=error):
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


@pytest.mark.asyncio
async def test_regression_523f_webp_is_normalized_for_provider_only(tmp_path, monkeypatch):
    """Production 523f…: a valid owned WebP must not fail Seedance admission."""
    import uuid
    from types import SimpleNamespace

    from app.providers.neironych_submission import SNAPSHOT_KEY
    from app.services.neironych_generation_provider import NeironychGenerationProviderService
    from app.services.reference_static import ReferenceStaticStorage

    root = tmp_path / "refs"
    root.mkdir()
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setattr(settings, "public_base_url", "https://ksu.example")
    original = root / "523f4b46-d1df-4e60-879b-fc1ab1ec194e.webp"
    Image.new("RGB", (1280, 1707), (61, 72, 83)).save(original, format="WEBP")
    original_bytes = original.read_bytes()
    original_url = ReferenceStaticStorage.public_url(original.name)
    generation = SimpleNamespace(
        id=uuid.UUID("523f4b46-d1df-4e60-879b-fc1ab1ec194e"),
        input_url=None,
        action_type="generate",
        prompt="Animate the photograph",
        parameters={
            "_model_id": "seedance-2.5",
            "reference_image_urls": [original_url],
            "duration": 6,
            "resolution": "480p",
            "aspect_ratio": "3:4",
        },
    )

    await NeironychGenerationProviderService._freeze_new_submission(None, generation)

    provider_url = json.loads(generation.parameters[SNAPSHOT_KEY]["body_json"])[
        "reference_images"
    ][0]["url"]
    assert provider_url != original_url
    assert provider_url.startswith("https://ksu.example/uploads/refs/normalized/")
    normalized = ReferenceStaticStorage.path_for_url(provider_url)
    assert normalized is not None and normalized.is_file()
    with Image.open(normalized) as image:
        assert image.format in {"JPEG", "PNG"}
        assert image.size == (1280, 1707)
        image.verify()
    assert original.read_bytes() == original_bytes
    assert generation.parameters["reference_image_urls"] == [original_url]


@pytest.mark.asyncio
async def test_regression_86ea_heic_is_normalized_and_reference_order_is_preserved(
    tmp_path, monkeypatch,
):
    """Production 86ea…: HEIC + JPEG stays in order and reaches Seedance."""
    import uuid
    from types import SimpleNamespace

    from pillow_heif import from_pillow

    from app.providers.neironych_submission import SNAPSHOT_KEY
    from app.services.neironych_generation_provider import NeironychGenerationProviderService
    from app.services.reference_static import ReferenceStaticStorage

    root = tmp_path / "refs"
    root.mkdir()
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setattr(settings, "public_base_url", "https://ksu.example")
    heic_path = root / "86ea5e0c-7600-47b8-8dc2-ba8609d5709e.heic"
    source = Image.new("RGB", (900, 1200), (17, 34, 51))
    try:
        from_pillow(source).save(heic_path, quality=90)
    finally:
        source.close()
    heic_bytes = heic_path.read_bytes()
    jpeg_path = root / "second.jpg"
    Image.new("RGB", (1200, 900), (68, 85, 102)).save(jpeg_path, format="JPEG")
    heic_url = ReferenceStaticStorage.public_url(heic_path.name)
    jpeg_url = ReferenceStaticStorage.public_url(jpeg_path.name)
    generation = SimpleNamespace(
        id=uuid.UUID("86ea5e0c-7600-47b8-8dc2-ba8609d5709e"),
        input_url=None,
        action_type="generate",
        prompt="Animate both photographs",
        parameters={
            "_model_id": "seedance-2.5",
            "reference_image_urls": [heic_url, jpeg_url],
            "duration": 6,
            "resolution": "480p",
            "aspect_ratio": "3:4",
        },
    )

    await NeironychGenerationProviderService._freeze_new_submission(None, generation)

    provider_urls = [
        item["url"]
        for item in json.loads(generation.parameters[SNAPSHOT_KEY]["body_json"])[
            "reference_images"
        ]
    ]
    assert provider_urls[0] != heic_url
    assert provider_urls[1] == jpeg_url
    normalized = ReferenceStaticStorage.path_for_url(provider_urls[0])
    assert normalized is not None and normalized.is_file()
    with Image.open(normalized) as image:
        assert image.format in {"JPEG", "PNG"}
        assert image.size == (900, 1200)
        image.verify()
    assert heic_path.read_bytes() == heic_bytes
    assert generation.parameters["reference_image_urls"] == [heic_url, jpeg_url]


@pytest.mark.parametrize("actual_format,suffix", [("JPEG", ".webp"), ("PNG", ".jpg")])
@pytest.mark.asyncio
async def test_valid_jpeg_png_bytes_pass_through_even_with_wrong_suffix(
    tmp_path, monkeypatch, actual_format, suffix,
):
    from app.services.reference_static import ReferenceStaticStorage

    root = tmp_path / "refs"
    root.mkdir()
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setattr(settings, "public_base_url", "https://ksu.example")
    path = root / f"mislabeled{suffix}"
    Image.new("RGB", (600, 800), (3, 6, 9)).save(path, format=actual_format)
    url = ReferenceStaticStorage.public_url(path.name)
    payload = {"reference_images": [{"url": url}]}

    await normalize_seedance_image_references("seedance-2.5", payload)

    assert payload == {"reference_images": [{"url": url}]}
    assert not (root / "normalized").exists()


@pytest.mark.asyncio
async def test_corrupt_jpeg_fails_closed_without_normalized_artifact(tmp_path, monkeypatch):
    from app.services.reference_static import ReferenceStaticStorage

    root = tmp_path / "refs"
    root.mkdir()
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setattr(settings, "public_base_url", "https://ksu.example")
    path = root / "broken.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0truncated-jpeg")
    payload = {"reference_images": [{"url": ReferenceStaticStorage.public_url(path.name)}]}

    with pytest.raises(ReferenceValidationError, match="valid image"):
        await normalize_seedance_image_references("seedance-2.5", payload)

    assert not (root / "normalized").exists()


@pytest.mark.asyncio
async def test_webp_exif_orientation_is_applied_to_normalized_geometry(tmp_path, monkeypatch):
    from app.services.reference_static import ReferenceStaticStorage

    root = tmp_path / "refs"
    root.mkdir()
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setattr(settings, "public_base_url", "https://ksu.example")
    path = root / "rotated.webp"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (600, 800), (20, 40, 60)).save(path, format="WEBP", exif=exif)
    payload = {"reference_images": [{"url": ReferenceStaticStorage.public_url(path.name)}]}

    await normalize_seedance_image_references("seedance-2.5", payload)

    target = ReferenceStaticStorage.path_for_url(payload["reference_images"][0]["url"])
    assert target is not None
    with Image.open(target) as image:
        assert image.size == (800, 600)
        assert image.getexif().get(274, 1) == 1


@pytest.mark.asyncio
async def test_external_normalization_failure_is_retryable(monkeypatch):
    async def unavailable(*_args, **_kwargs):
        raise httpx.ReadTimeout("reference read timed out")

    monkeypatch.setattr(
        "app.services.neironych_reference_validation._normalize_image_url", unavailable
    )
    with pytest.raises(ReferenceValidationUnavailable, match="unavailable"):
        await normalize_seedance_image_references(
            "seedance-2.5",
            {"reference_images": [{"url": "https://media.example/ref.webp"}]},
        )


@pytest.mark.asyncio
async def test_atomic_storage_failure_is_retryable_and_leaves_no_partial_file(
    tmp_path, monkeypatch,
):
    from app.services.reference_static import ReferenceStaticStorage

    root = tmp_path / "refs"
    root.mkdir()
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setattr(settings, "public_base_url", "https://ksu.example")
    path = root / "storage-failure.webp"
    Image.new("RGB", (600, 800), (7, 8, 9)).save(path, format="WEBP")
    payload = {"reference_images": [{"url": ReferenceStaticStorage.public_url(path.name)}]}

    def fail_replace(*_args):
        raise PermissionError("synthetic unavailable storage")

    monkeypatch.setattr("app.services.neironych_reference_validation.os.replace", fail_replace)
    with pytest.raises(ReferenceValidationUnavailable, match="unavailable"):
        await normalize_seedance_image_references("seedance-2.5", payload)

    normalized = root / "normalized"
    assert normalized.is_dir()
    assert list(normalized.iterdir()) == []


@pytest.mark.parametrize("action_type", ["generate", "trend", "repeat"])
@pytest.mark.asyncio
async def test_customer_generation_trend_and_repeat_share_snapshot_normalization(
    tmp_path, monkeypatch, action_type,
):
    import uuid
    from types import SimpleNamespace

    from app.providers.neironych_submission import SNAPSHOT_KEY
    from app.services.neironych_generation_provider import NeironychGenerationProviderService
    from app.services.reference_static import ReferenceStaticStorage

    root = tmp_path / "refs"
    root.mkdir()
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setattr(settings, "public_base_url", "https://ksu.example")
    path = root / f"{action_type}.webp"
    Image.new("RGB", (600, 800), (90, 60, 30)).save(path, format="WEBP")
    original_url = ReferenceStaticStorage.public_url(path.name)
    row = SimpleNamespace(
        id=uuid.uuid4(),
        input_url=None,
        action_type=action_type,
        prompt="Animate",
        parameters={
            "_model_id": "seedance-2.5",
            "reference_image_urls": [original_url],
            "duration": 6,
            "resolution": "480p",
            "aspect_ratio": "3:4",
        },
    )

    await NeironychGenerationProviderService._freeze_new_submission(None, row)

    provider_url = json.loads(row.parameters[SNAPSHOT_KEY]["body_json"])[
        "reference_images"
    ][0]["url"]
    assert provider_url != original_url
    assert row.parameters["reference_image_urls"] == [original_url]
