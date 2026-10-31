from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from app.core.config import settings
from app.services.feed_static import FeedStaticStorage
from app.services.media_assets import MediaIngestService
from app.services.media_probe import probe_media_stream
from app.services.reference_static import ReferenceStaticStorage


register_heif_opener(thumbnails=False)


class ReferenceValidationError(ValueError):
    pass


class ReferenceValidationUnavailable(RuntimeError):
    pass


def byte_limit(model: str, kind: str) -> int:
    if kind == "image":
        return 20 * 1024 * 1024
    if kind == "audio":
        return 15_000_000
    return 100 * 1024 * 1024 if model == "seedance-2.5" else 50_000_000


def _check_image_dimensions(model: str, width: int, height: int) -> None:
    """Enforce model image limits before decoding an MPO or reading a JPEG."""
    if model == "seedance-2.5" and not (
        300 <= width <= 6000
        and 300 <= height <= 6000
        and 0.4 <= width / height <= 2.5
    ):
        raise ReferenceValidationError(
            "Seedance 2.5 images require 300-6000 px per side and ratio 0.4-2.5"
        )


def _check_normalization_dimensions(model: str, width: int, height: int) -> None:
    """Reject oversized images before Pillow allocates a decoded buffer.

    Seedance 2.5 uses its exact provider contract. For Seedance 2.0, cap
    conversion at that same bounded size: these formats were previously unsupported.
    """
    _check_image_dimensions(model, width, height)
    if not (0 < width <= 6000 and 0 < height <= 6000):
        raise ReferenceValidationError(
            "Seedance image exceeds safe normalization dimensions (6000 px per side)"
        )


def inspect_file(model: str, kind: str, path: Path) -> float:
    """Inspect real bytes, not MIME/extension or the success of an HTTP GET.

    Returns measured seconds for aggregate media limits (zero for images).
    No reference content or private URL is included in validation errors.
    """
    size = path.stat().st_size
    if not 0 < size <= byte_limit(model, kind):
        raise ReferenceValidationError(
            f"Seedance {kind} reference exceeds file size limit or is empty"
        )
    if kind == "image":
        try:
            with Image.open(path) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise ReferenceValidationError("Seedance image references must be JPEG or PNG")
                _check_image_dimensions(model, *image.size)
                image.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
            raise ReferenceValidationError(
                "Seedance image reference is not a valid JPEG/PNG"
            ) from exc
        return 0.0
    with path.open("rb") as stream:
        probe = probe_media_stream(stream, filename=path.name)
    if probe.status != "ready" or not probe.duration_ms:
        raise ReferenceValidationError("Seedance reference metadata could not be verified")
    seconds = probe.duration_ms / 1000
    maximum = 30 if model == "seedance-2.5" else 15
    if not 2 <= seconds <= maximum:
        raise ReferenceValidationError(
            f"Seedance {kind} reference duration must be 2-{maximum} seconds"
        )
    containers = set((probe.container or "").split(","))
    if kind == "audio":
        if not containers.intersection({"wav", "mp3"}) or not probe.audio_codec:
            raise ReferenceValidationError("Seedance audio references must be WAV or MP3")
        return seconds
    if not containers.intersection({"mov", "mp4"}) or not probe.video_codec:
        raise ReferenceValidationError("Seedance video references must be MP4 or MOV")
    width, height = probe.width or 0, probe.height or 0
    if model == "seedance-2.5":
        if not (
            300 <= width <= 6000
            and 300 <= height <= 6000
            and 409600 <= width * height <= 8295044
            and 0.4 <= width / max(1, height) <= 2.5
        ):
            raise ReferenceValidationError(
                "Seedance 2.5 video dimensions do not satisfy the documented limits"
            )
        if probe.fps is None or not 24 <= probe.fps <= 60:
            raise ReferenceValidationError("Seedance 2.5 videos require 24-60 fps")
    elif not (200 <= width <= 2160 and 200 <= height <= 2160):
        raise ReferenceValidationError("Seedance 2.0 video sides must be 200-2160 px")
    return seconds


def inspect_upload(model: str, kind: str, content: bytes, mime: str) -> None:
    # Immediate ticket upload validates the bytes; task admission also verifies
    # aggregate durations and combinations, which cannot be checked per file.
    suffix = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
    }.get(mime)
    if suffix is None:
        raise ReferenceValidationError("Unsupported Seedance reference MIME type")
    temporary = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    path = Path(temporary.name)
    try:
        temporary.write(content)
        temporary.flush()
        temporary.close()
        inspect_file(model, kind, path)
    finally:
        temporary.close()
        path.unlink(missing_ok=True)


def _image_conversion_format(model: str, path: Path) -> str | None:
    """Return the needed wire format, or None for valid JPEG/PNG bytes."""
    size = path.stat().st_size
    if not 0 < size <= byte_limit(model, "image"):
        raise ReferenceValidationError(
            "Seedance image reference exceeds file size limit or is empty"
        )
    try:
        with Image.open(path) as source:
            source_format = source.format
            if source_format in {"JPEG", "PNG"}:
                _check_image_dimensions(model, *source.size)
                source.verify()
                return None
            _check_normalization_dimensions(model, *source.size)
            return (
                "PNG"
                if source.mode in {"RGBA", "LA"}
                or (source.mode == "P" and "transparency" in source.info)
                else "JPEG"
            )
    except ReferenceValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ReferenceValidationError("Seedance image reference is not a valid image") from exc


def _transcode_image(source_path: Path, target: Any, *, output_format: str) -> None:
    """Decode one image, apply its orientation, and emit one supported wire image."""
    try:
        with Image.open(source_path) as source:
            if source.format == "MPO":
                source.seek(0)
            normalized = ImageOps.exif_transpose(source)
            converted = (
                normalized.convert("RGBA")
                if output_format == "PNG"
                else normalized.convert("RGB")
            )
    except ReferenceValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ReferenceValidationError("Seedance image reference is not a valid image") from exc
    try:
        save_options = (
            {"format": "PNG", "optimize": True}
            if output_format == "PNG"
            else {"format": "JPEG", "quality": 92, "optimize": True}
        )
        try:
            converted.save(target, **save_options)
        except OSError as exc:
            raise ReferenceValidationUnavailable(
                "Seedance image normalization output is unavailable"
            ) from exc
    finally:
        converted.close()


def normalize_seedance_image_upload(model: str, content: bytes) -> tuple[bytes, str]:
    """Normalize admin-upload bytes and return their actual supported MIME."""
    if not 0 < len(content) <= byte_limit(model, "image"):
        raise ReferenceValidationError(
            "Seedance image reference exceeds file size limit or is empty"
        )
    source = tempfile.NamedTemporaryFile(prefix=".roxy-upload-source-", delete=False)
    source_path = Path(source.name)
    target_path: Path | None = None
    try:
        source.write(content)
        source.flush()
        source.close()
        output_format = _image_conversion_format(model, source_path)
        if output_format is None:
            with Image.open(source_path) as image:
                mime = "image/png" if image.format == "PNG" else "image/jpeg"
            return content, mime
        suffix = ".png" if output_format == "PNG" else ".jpg"
        target = tempfile.NamedTemporaryFile(
            prefix=".roxy-upload-normalized-", suffix=suffix, delete=False
        )
        target_path = Path(target.name)
        try:
            _transcode_image(source_path, target, output_format=output_format)
            target.flush()
            os.fsync(target.fileno())
        finally:
            target.close()
        inspect_file(model, "image", target_path)
        return target_path.read_bytes(), f"image/{output_format.lower()}"
    finally:
        source.close()
        source_path.unlink(missing_ok=True)
        if target_path is not None:
            target_path.unlink(missing_ok=True)


def owned_path(url: str) -> Path | None:
    parsed = urlsplit(url)
    base = urlsplit(settings.public_base_url)
    # is_local_url historically only checks path. Never treat an arbitrary
    # external host with an /uploads/refs path as a trusted local file.
    if parsed.scheme and (parsed.scheme != "https" or parsed.netloc != base.netloc):
        return None
    for storage in (ReferenceStaticStorage, FeedStaticStorage):
        if storage.is_local_url(url):
            path = storage.path_for_url(url)
            if path is None or not path.is_file():
                raise ReferenceValidationError("Stored Seedance reference is missing")
            return path
    return None


async def _download_url_to_path(
    client: httpx.AsyncClient,
    model: str,
    kind: str,
    url: str,
    path: Path,
) -> None:
    """Stream one untrusted public reference into a bounded temporary file."""
    current = url
    # No provider/Telegram key is sent to reference hosts. Reuse the existing
    # public HTTPS/SSRF guard at every redirect; preserve signed query bytes.
    for _ in range(settings.media_ingest_max_redirects + 1):
        await MediaIngestService._validate_public_https_url(current)
        async with client.stream("GET", current) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise ReferenceValidationError("Reference redirect has no target")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            raw_size = response.headers.get("content-length", "")
            limit = byte_limit(model, kind)
            if raw_size.isdecimal() and int(raw_size) > limit:
                raise ReferenceValidationError("Seedance reference is too large")
            with path.open("wb") as temporary:
                size = 0
                async for chunk in response.aiter_bytes(64 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise ReferenceValidationError("Seedance reference is too large")
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            return
    raise ReferenceValidationError("Too many Seedance reference redirects")


async def _inspect_url(client: httpx.AsyncClient, model: str, kind: str, url: str) -> float:
    path = owned_path(url)
    if path is not None:
        return await asyncio.to_thread(inspect_file, model, kind, path)
    suffix = {"image": ".image", "video": ".video", "audio": ".audio"}[kind]
    temporary = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    temp_path = Path(temporary.name)
    temporary.close()
    try:
        await _download_url_to_path(client, model, kind, url, temp_path)
        return await asyncio.to_thread(inspect_file, model, kind, temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


def _normalize_image_path(model: str, path: Path, original_url: str) -> str:
    """Make an immutable JPEG/PNG transport copy of an image when needed.

    The user's original reference URL/bytes stay untouched for trends, repeats
    and any other provider. Only the frozen Neironych request uses the copy.
    """
    size = path.stat().st_size
    if not 0 < size <= byte_limit(model, "image"):
        raise ReferenceValidationError(
            "Seedance image reference exceeds file size limit or is empty"
        )
    try:
        # Pillow detects the real container from bytes, not extension/MIME.
        output_format = _image_conversion_format(model, path)
        if output_format is None:
            return original_url

        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        directory = ReferenceStaticStorage.ensure_root() / "normalized"
        directory.mkdir(parents=True, exist_ok=True)
        suffix = ".png" if output_format == "PNG" else ".jpg"
        filename = f"{digest.hexdigest()}-seedance-v1{suffix}"
        target = directory / filename
        normalized_url = ReferenceStaticStorage.public_url(f"normalized/{filename}")
        if target.is_file():
            inspect_file(model, "image", target)
            return normalized_url

        # Only cache misses decode/transcode the image. Never change source.
        # Atomic replacement avoids partial reads by the provider/static app.
        temporary = tempfile.NamedTemporaryFile(
            prefix=".roxy-image-", suffix=suffix, dir=directory, delete=False
        )
        temp_path = Path(temporary.name)
        try:
            _transcode_image(path, temporary, output_format=output_format)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary.close()
            inspect_file(model, "image", temp_path)
            os.replace(temp_path, target)
            os.chmod(target, 0o644)
        finally:
            temporary.close()
            temp_path.unlink(missing_ok=True)
        return normalized_url
    except ReferenceValidationError:
        raise
    except (UnidentifiedImageError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ReferenceValidationError(
            "Seedance image reference is not a valid JPEG/PNG"
        ) from exc
    except OSError as exc:
        raise ReferenceValidationUnavailable(
            "Seedance image normalization is unavailable"
        ) from exc


async def _normalize_image_url(
    client: httpx.AsyncClient, model: str, url: str
) -> str:
    path = owned_path(url)
    if path is not None:
        return await asyncio.to_thread(_normalize_image_path, model, path, url)
    temporary = tempfile.NamedTemporaryFile(suffix=".image", delete=False)
    temp_path = Path(temporary.name)
    temporary.close()
    try:
        await _download_url_to_path(client, model, "image", url, temp_path)
        return await asyncio.to_thread(_normalize_image_path, model, temp_path, url)
    finally:
        temp_path.unlink(missing_ok=True)

async def normalize_seedance_image_references(model: str, payload: dict[str, Any]) -> set[str]:
    """Normalize unsupported images before validation and snapshot freeze."""
    images = list(payload.get("reference_images", []))
    images.extend(
        payload[key] for key in ("start_image", "end_image") if payload.get(key)
    )
    if not images:
        return set()
    validated: set[str] = set()
    try:
        async with asyncio.timeout(settings.neironych_reference_validation_timeout_seconds):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(20, connect=10),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                for image in images:
                    image["url"] = await _normalize_image_url(client, model, image["url"])
                    validated.add(image["url"])
    except TimeoutError as exc:
        raise ReferenceValidationUnavailable(
            "Seedance image normalization timed out"
        ) from exc
    except (httpx.HTTPError, OSError) as exc:
        raise ReferenceValidationUnavailable(
            f"Seedance image normalization unavailable ({type(exc).__name__})"
        ) from None
    return validated


async def validate_reference_payload(
    model: str,
    payload: dict[str, Any],
    *,
    validated_image_urls: set[str] | None = None,
) -> None:
    entries: list[tuple[str, str]] = []
    for kind in ("image", "video", "audio"):
        entries.extend((kind, item["url"]) for item in payload.get(f"reference_{kind}s", []))
    entries.extend(
        ("image", payload[field]["url"])
        for field in ("start_image", "end_image")
        if payload.get(field)
    )
    if not entries:
        return
    total = {"video": 0.0, "audio": 0.0}
    validated_images = validated_image_urls or set()
    try:
        async with asyncio.timeout(settings.neironych_reference_validation_timeout_seconds):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(20, connect=10), follow_redirects=False, trust_env=False
            ) as client:
                first_video = True
                for kind, url in entries:
                    if kind == "image" and url in validated_images:
                        continue
                    duration = await _inspect_url(client, model, kind, url)
                    if kind in total:
                        total[kind] += duration
                        if (
                            kind == "video"
                            and first_video
                            and payload.get("omni_reference_task_type") == "edit"
                            and duration < 4
                        ):
                            raise ReferenceValidationError(
                                "Seedance edit source must be at least 4 seconds"
                            )
                        if kind == "video":
                            first_video = False
    except (httpx.HTTPError, TimeoutError, OSError) as exc:
        raise ReferenceValidationUnavailable(
            f"Seedance reference validation unavailable ({type(exc).__name__})"
        ) from None
    maximum = 30 if model == "seedance-2.5" else 15
    if any(value > maximum for value in total.values()):
        raise ReferenceValidationError(
            f"Seedance total video/audio reference duration exceeds {maximum} seconds"
        )
