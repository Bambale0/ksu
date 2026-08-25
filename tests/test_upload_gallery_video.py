from __future__ import annotations

import io
from dataclasses import dataclass

from app.api.v1.uploads import _upload_content_type, _upload_size


@dataclass
class DummyUpload:
    filename: str | None
    content_type: str | None
    body: bytes

    def __post_init__(self) -> None:
        self.file = io.BytesIO(self.body)


def test_gallery_mov_octet_stream_is_treated_as_video() -> None:
    upload = DummyUpload(
        filename="IMG_1234.MOV",
        content_type="application/octet-stream",
        body=b"movie-bytes",
    )

    assert _upload_content_type(upload) == "video/quicktime"  # type: ignore[arg-type]
    assert _upload_size(upload) == len(b"movie-bytes")  # type: ignore[arg-type]
    assert upload.file.tell() == 0


def test_gallery_mp4_without_declared_mime_is_treated_as_video() -> None:
    upload = DummyUpload(
        filename="gallery-export.mp4",
        content_type="",
        body=b"mp4-bytes",
    )

    assert _upload_content_type(upload) == "video/mp4"  # type: ignore[arg-type]


def test_declared_video_mime_is_preserved_without_parameters() -> None:
    upload = DummyUpload(
        filename="clip.mov",
        content_type="Video/QuickTime; charset=binary",
        body=b"mov-bytes",
    )

    assert _upload_content_type(upload) == "video/quicktime"  # type: ignore[arg-type]


def test_octet_stream_without_media_extension_stays_unsupported() -> None:
    upload = DummyUpload(
        filename="blob",
        content_type="application/octet-stream",
        body=b"unknown",
    )

    assert _upload_content_type(upload) == "application/octet-stream"  # type: ignore[arg-type]
