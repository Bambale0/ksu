from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.services.feed_static import FeedStaticStorage
from app.services.media_assets import MediaIngestService
from app.services.media_probe import probe_media_stream
from app.services.reference_static import ReferenceStaticStorage


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
                width, height = image.size
                if model == "seedance-2.5" and not (
                    300 <= width <= 6000 and 300 <= height <= 6000 and 0.4 <= width / height <= 2.5
                ):
                    raise ReferenceValidationError(
                        "Seedance 2.5 images require 300-6000 px per side and ratio 0.4-2.5"
                    )
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
    with tempfile.NamedTemporaryFile(suffix=suffix) as temporary:
        temporary.write(content)
        temporary.flush()
        inspect_file(model, kind, Path(temporary.name))


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


async def _inspect_url(client: httpx.AsyncClient, model: str, kind: str, url: str) -> float:
    path = owned_path(url)
    if path is not None:
        return await asyncio.to_thread(inspect_file, model, kind, path)
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
            suffix = {"image": ".jpg", "video": ".mp4", "audio": ".mp3"}[kind]
            with tempfile.NamedTemporaryFile(suffix=suffix) as temporary:
                size = 0
                async for chunk in response.aiter_bytes(64 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise ReferenceValidationError("Seedance reference is too large")
                    temporary.write(chunk)
                temporary.flush()
                return await asyncio.to_thread(inspect_file, model, kind, Path(temporary.name))
    raise ReferenceValidationError("Too many Seedance reference redirects")


async def validate_reference_payload(model: str, payload: dict[str, Any]) -> None:
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
    try:
        async with asyncio.timeout(settings.neironych_reference_validation_timeout_seconds):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(20, connect=10), follow_redirects=False, trust_env=False
            ) as client:
                first_video = True
                for kind, url in entries:
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
