from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

from PIL import Image, ImageOps

from app.services.reference_static import ReferenceStaticStorage

_MAX_EDGE = 320
_WEBP_QUALITY = 72
_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v", ".qt", ".quicktime"}


class ReferencePreviewService:
    @staticmethod
    def root() -> Path:
        root = ReferenceStaticStorage.ensure_root() / ".thumbs"
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def thumbnail_path(cls, source_url: str) -> Path | None:
        source = ReferenceStaticStorage.path_for_url(source_url)
        if source is None or not source.is_file():
            return None
        target = cls.root() / f"{source.stem}.webp"
        if target.is_file() and target.stat().st_size > 0:
            return target

        temp = target.with_name(f"{target.stem}-{uuid.uuid4().hex}.tmp.webp")
        try:
            if source.suffix.lower() in _VIDEO_SUFFIXES:
                ffmpeg = shutil.which("ffmpeg")
                if ffmpeg is None:
                    return None
                subprocess.run(
                    [
                        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                        "-protocol_whitelist", "file,pipe", "-i", str(source),
                        "-frames:v", "1", "-vf",
                        f"scale={_MAX_EDGE}:{_MAX_EDGE}:force_original_aspect_ratio=decrease",
                        "-c:v", "libwebp", "-quality", str(_WEBP_QUALITY), "-y", str(temp),
                    ],
                    check=True, capture_output=True, timeout=10,
                )
            else:
                with Image.open(source) as opened:
                    image = ImageOps.exif_transpose(opened)
                    image.load()
                    if image.mode not in {"RGB", "RGBA"}:
                        converted = image.convert("RGBA" if "transparency" in image.info else "RGB")
                        if image is not opened:
                            image.close()
                        image = converted
                    image.thumbnail((_MAX_EDGE, _MAX_EDGE), Image.Resampling.LANCZOS)
                    image.save(temp, "WEBP", quality=_WEBP_QUALITY, method=6)
                    if image is not opened:
                        image.close()
            if not temp.is_file() or temp.stat().st_size == 0:
                temp.unlink(missing_ok=True)
                return None
            os.replace(temp, target)
            try:
                os.chmod(target, 0o644)
            except OSError:
                pass
            return target
        except (OSError, ValueError, subprocess.SubprocessError, Image.UnidentifiedImageError):
            temp.unlink(missing_ok=True)
            return None
