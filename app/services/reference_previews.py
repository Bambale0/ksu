from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageOps

from app.services.reference_static import ReferenceStaticStorage

_MAX_EDGE = 320
_WEBP_QUALITY = 72


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

        temp = target.with_suffix(".tmp.webp")
        try:
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
            os.replace(temp, target)
            try:
                os.chmod(target, 0o644)
            except OSError:
                pass
            return target
        except Exception:
            temp.unlink(missing_ok=True)
            return None
