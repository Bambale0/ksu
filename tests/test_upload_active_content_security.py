from __future__ import annotations

import hashlib
import io
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from starlette.responses import Response

from app.api.v1.uploads import _upload_content_type
from app.core.http_security import REFERENCE_STATIC_CSP, SecurityHeadersMiddleware
from app.services.reference_static import ReferenceStaticStorage, ReferenceStaticStorageError


@dataclass
class DummyUpload:
    filename: str | None
    content_type: str | None
    body: bytes = b"payload"

    def __post_init__(self) -> None:
        self.file = io.BytesIO(self.body)


def test_user_filename_cannot_turn_image_upload_into_html(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path))
    body = b"not-a-real-png-but-passive-for-storage-boundary"
    digest = hashlib.sha256(body).hexdigest()

    url, target, size = ReferenceStaticStorage.persist_stream(
        io.BytesIO(body),
        user_id=uuid.uuid4(),
        kind="image",
        file_hash=digest,
        filename="evil.html",
        content_type="image/png",
        expected_size=len(body),
    )

    assert size == len(body)
    assert url.endswith(f"{digest}.png")
    assert target.suffix == ".png"
    assert not url.endswith(".html")


def test_active_document_media_types_are_not_supported() -> None:
    for content_type in (
        "image/svg+xml",
        "text/html",
        "application/xhtml+xml",
        "application/xml",
        "text/xml",
    ):
        assert not ReferenceStaticStorage.supports_content_type(content_type)

    with pytest.raises(ReferenceStaticStorageError, match="Unsupported reference media type"):
        ReferenceStaticStorage._extension(
            filename="picture.svg",
            content_type="image/svg+xml",
        )


def test_svg_declared_as_image_is_rejected_by_upload_contract() -> None:
    upload = DummyUpload(filename="vector.svg", content_type="image/svg+xml")
    content_type = _upload_content_type(upload)  # type: ignore[arg-type]

    assert content_type == "image/svg+xml"
    assert not ReferenceStaticStorage.supports_content_type(content_type)


def test_octet_stream_keeps_safe_gallery_fallback() -> None:
    upload = DummyUpload(filename="gallery-export.MP4", content_type="application/octet-stream")

    assert _upload_content_type(upload) == "video/mp4"  # type: ignore[arg-type]
    assert ReferenceStaticStorage.supports_content_type("video/mp4")


def test_reference_static_responses_are_sandboxed_for_legacy_files() -> None:
    response = Response()
    secured = SecurityHeadersMiddleware._secure_response(
        response,
        "12345678",
        "/uploads/refs/image/user/2026/09/legacy.html",
    )

    assert secured.headers["Content-Security-Policy"] == REFERENCE_STATIC_CSP
    assert "sandbox" in REFERENCE_STATIC_CSP
    assert "default-src 'none'" in REFERENCE_STATIC_CSP
    assert "form-action 'none'" in REFERENCE_STATIC_CSP
    assert secured.headers["X-Content-Type-Options"] == "nosniff"
