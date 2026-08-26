from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

from app.providers.kie_prompt_tools import PromptToolProviderError
from app.providers.tanyapi_video_prompt import (
    VIDEO_PROMPT_FRAME_TIMEOUT_SECONDS,
    VIDEO_PROMPT_MAX_DURATION_SECONDS,
)


def probe_video_duration_seconds(video_bytes: bytes) -> float:
    """Read the source clip duration from the actual bytes with ffprobe.

    Mini App uploads do not carry Telegram's trusted ``video.duration`` metadata.
    Probe the stored/provider transport itself so the tanyapi six-frame fallback is
    sampled across the whole clip and the 60-second product limit is authoritative.
    """

    if not video_bytes:
        raise PromptToolProviderError("Видео пустое")

    with tempfile.TemporaryDirectory(prefix="video_prompt_probe_") as temp_dir:
        path = Path(temp_dir) / "source_video"
        path.write_bytes(video_bytes)
        command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        try:
            completed = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=VIDEO_PROMPT_FRAME_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise PromptToolProviderError("ffprobe недоступен для анализа видео") from exc
        except subprocess.TimeoutExpired as exc:
            raise PromptToolProviderError("Не удалось определить длительность видео: timeout") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
            raise PromptToolProviderError(
                f"Не удалось прочитать видео: {stderr[:300] or 'ffprobe error'}"
            ) from exc

    raw = (completed.stdout or b"").decode("utf-8", errors="replace").strip()
    try:
        duration = float(raw)
    except (TypeError, ValueError) as exc:
        raise PromptToolProviderError("Не удалось определить длительность видео") from exc

    if not math.isfinite(duration) or duration <= 0:
        raise PromptToolProviderError("Не удалось определить длительность видео")
    if duration > VIDEO_PROMPT_MAX_DURATION_SECONDS:
        raise PromptToolProviderError(
            f"Видео должно быть не длиннее {VIDEO_PROMPT_MAX_DURATION_SECONDS} секунд"
        )
    return duration
