from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, ImageOps

from app.services.feed_static import FeedStaticStorage
from app.services.reference_static import ReferenceStaticStorage


def _local_path(source: str) -> Path | None:
    for storage in (ReferenceStaticStorage, FeedStaticStorage):
        path = storage.path_for_url(source)
        if path is not None:
            return path
    return None


def image_source_to_analysis_input(source: str | None, *, max_edge: int = 2048) -> str | None:
    """Prepare a ROXY-owned image for Kie vision calls without exposing local URLs.

    Ported from the proven ``banano_kling:tanyapi`` photo-analysis transport:
    locally persisted uploads are EXIF-normalized, bounded to 2048px and encoded
    as a JPEG data URI. External HTTPS/data URLs pass through unchanged.
    """

    value = str(source or "").strip()
    if not value or value.startswith("data:image/"):
        return value or None

    local_path = _local_path(value)
    if local_path is None:
        return value
    if not local_path.is_file() or local_path.stat().st_size <= 0:
        raise FileNotFoundError("Stored photo reference is missing")

    try:
        with Image.open(local_path) as image:
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            edge = max(256, int(max_edge))
            normalized.thumbnail((edge, edge), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            normalized.save(output, format="JPEG", quality=90, optimize=True)
    except Exception as exc:  # Pillow exposes several format-specific exceptions.
        raise ValueError("Stored photo reference cannot be decoded") from exc

    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
