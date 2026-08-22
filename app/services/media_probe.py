from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Any


@dataclass(frozen=True, slots=True)
class MediaProbe:
    status: str
    duration_ms: int | None = None
    width: int | None = None
    height: int | None = None
    container: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None

    @property
    def duration_seconds(self) -> int | None:
        if self.duration_ms is None or self.duration_ms <= 0:
            return None
        return max(1, math.ceil(self.duration_ms / 1000))


def _positive_int(value: Any) -> int | None:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def _seconds(value: Any) -> float | None:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(normalized) or normalized <= 0:
        return None
    return normalized


def _parse_probe(payload: dict[str, Any]) -> MediaProbe:
    streams = payload.get("streams")
    streams = streams if isinstance(streams, list) else []
    format_info = payload.get("format")
    format_info = format_info if isinstance(format_info, dict) else {}

    video = next(
        (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"),
        {},
    )
    audio = next(
        (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"),
        {},
    )

    duration_candidates = [_seconds(format_info.get("duration"))]
    duration_candidates.extend(
        _seconds(item.get("duration"))
        for item in streams
        if isinstance(item, dict)
    )
    duration_values = [value for value in duration_candidates if value is not None]
    duration_ms = math.ceil(max(duration_values) * 1000) if duration_values else None

    container = str(format_info.get("format_name") or "").strip() or None
    video_codec = str(video.get("codec_name") or "").strip() or None
    audio_codec = str(audio.get("codec_name") or "").strip() or None

    return MediaProbe(
        status="ready",
        duration_ms=duration_ms,
        width=_positive_int(video.get("width")),
        height=_positive_int(video.get("height")),
        container=container[:64] if container else None,
        video_codec=video_codec[:64] if video_codec else None,
        audio_codec=audio_codec[:64] if audio_codec else None,
    )


def probe_media_stream(stream: BinaryIO, filename: str = "upload") -> MediaProbe:
    """Probe media with ffprobe without trusting the multipart MIME declaration.

    Production images install ffprobe via the ffmpeg package. Probe failure does
    not make the upload disappear; the resulting reference is marked unverified
    and duration-derived billing will fail closed until verified metadata exists.
    """

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return MediaProbe(status="unavailable")

    suffix = Path(filename or "upload").suffix[:16]
    current = stream.tell()
    try:
        stream.seek(0)
        with tempfile.NamedTemporaryFile(prefix="roxy-probe-", suffix=suffix) as temporary:
            shutil.copyfileobj(stream, temporary)
            temporary.flush()
            command = [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration,format_name:stream=codec_type,codec_name,width,height,duration",
                "-of",
                "json",
                temporary.name,
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        if completed.returncode != 0:
            return MediaProbe(status="failed")
        payload = json.loads(completed.stdout or "{}")
        if not isinstance(payload, dict):
            return MediaProbe(status="failed")
        return _parse_probe(payload)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return MediaProbe(status="failed")
    finally:
        stream.seek(current)
