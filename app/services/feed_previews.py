from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from app.services.feed_static import FeedStaticStorage

_FEED_THUMB_MAX_SIDE = 768
_FEED_THUMB_MIN_BYTES = 50 * 1024
_FEED_THUMB_MAX_BYTES = 200 * 1024
_FEED_THUMB_MIN_QUALITY = 35
_FEED_THUMB_MAX_QUALITY = 90
_FEED_THUMB_BACKGROUND = (255, 255, 255)
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class FeedPreviewService:
    @staticmethod
    def root() -> Path:
        return FeedStaticStorage.ensure_root() / "thumbs"

    @classmethod
    def _paths(cls, source: Path) -> tuple[Path, Path]:
        return (
            cls.root() / f"{source.stem}.jpg",
            cls.root() / f"{source.stem}.webp",
        )

    @staticmethod
    def _has_alpha(image: Image.Image) -> bool:
        return image.mode in {"RGBA", "LA"} or (
            image.mode == "P" and "transparency" in image.info
        )

    @classmethod
    def _flatten(cls, image: Image.Image) -> Image.Image:
        if not cls._has_alpha(image):
            return image.convert("RGB")
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, _FEED_THUMB_BACKGROUND)
        background.paste(rgba, mask=rgba.getchannel("A"))
        rgba.close()
        return background

    @staticmethod
    def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
        buffer = BytesIO()
        image.save(
            buffer,
            "JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )
        return buffer.getvalue()

    @classmethod
    def _best_under_limit(cls, image: Image.Image) -> tuple[bytes, int]:
        low = _FEED_THUMB_MIN_QUALITY
        high = _FEED_THUMB_MAX_QUALITY
        best: tuple[bytes, int] | None = None
        while low <= high:
            quality = (low + high) // 2
            encoded = cls._encode_jpeg(image, quality)
            if len(encoded) <= _FEED_THUMB_MAX_BYTES:
                best = (encoded, quality)
                low = quality + 1
            else:
                high = quality - 1
        if best is not None:
            return best
        return cls._encode_jpeg(image, _FEED_THUMB_MIN_QUALITY), _FEED_THUMB_MIN_QUALITY

    @classmethod
    def _build(cls, source: Path) -> bytes:
        with Image.open(source) as opened:
            transposed = ImageOps.exif_transpose(opened)
            transposed.load()
        image = cls._flatten(transposed)
        if transposed is not opened:
            try:
                transposed.close()
            except Exception:
                pass
        image.thumbnail(
            (_FEED_THUMB_MAX_SIDE, _FEED_THUMB_MAX_SIDE),
            Image.Resampling.LANCZOS,
        )
        try:
            while True:
                encoded, _quality = cls._best_under_limit(image)
                if len(encoded) <= _FEED_THUMB_MAX_BYTES or max(image.size) <= 320:
                    return encoded
                next_size = (
                    max(1, round(image.width * 0.85)),
                    max(1, round(image.height * 0.85)),
                )
                resized = image.resize(next_size, Image.Resampling.LANCZOS)
                image.close()
                image = resized
        finally:
            image.close()

    @classmethod
    def _usable(cls, path: Path) -> bool:
        try:
            with Image.open(path) as image:
                image.load()
                return not cls._has_alpha(image)
        except Exception:
            return False

    @classmethod
    def preview_url_for(cls, media_url: str, *, create: bool = True) -> str | None:
        source = FeedStaticStorage.path_for_url(media_url)
        if source is None or not source.is_file() or source.suffix.lower() not in _IMAGE_SUFFIXES:
            return None
        if "thumbs" in source.parts:
            return media_url

        jpg, legacy_webp = cls._paths(source)
        if jpg.is_file() and cls._usable(jpg):
            return FeedStaticStorage.public_url_for(f"thumbs/{jpg.name}")
        if not create:
            return None

        cls.root().mkdir(parents=True, exist_ok=True)
        if jpg.exists():
            jpg.unlink(missing_ok=True)
        legacy_webp.unlink(missing_ok=True)
        temp = jpg.with_suffix(".tmp.jpg")
        try:
            encoded = cls._build(source)
            temp.write_bytes(encoded)
            os.replace(temp, jpg)
            try:
                os.chmod(jpg, 0o644)
            except OSError:
                pass
        except Exception:
            temp.unlink(missing_ok=True)
            return None
        return FeedStaticStorage.public_url_for(f"thumbs/{jpg.name}")

    @classmethod
    def remove_for(cls, media_url: str) -> None:
        source = FeedStaticStorage.path_for_url(media_url)
        if source is None:
            return
        jpg, webp = cls._paths(source)
        jpg.unlink(missing_ok=True)
        webp.unlink(missing_ok=True)

    @staticmethod
    def desired_min_bytes() -> int:
        return _FEED_THUMB_MIN_BYTES

    @staticmethod
    def max_bytes() -> int:
        return _FEED_THUMB_MAX_BYTES
