from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path

from app.core.config import settings
from app.services.reference_static import ReferenceStaticStorage


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\nroxy-reference-static"


def _persist(
    *,
    user_id: uuid.UUID,
    data: bytes,
    filename: str = "reference.png",
) -> tuple[str, Path, int]:
    return ReferenceStaticStorage.persist_stream(
        io.BytesIO(data),
        user_id=user_id,
        kind="image",
        file_hash=hashlib.sha256(data).hexdigest(),
        filename=filename,
        content_type="image/png",
        expected_size=len(data),
    )


def test_reference_upload_is_content_addressed_and_reused(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "refs"
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setenv("REFERENCE_STATIC_PUBLIC_PREFIX", "/uploads/refs")
    monkeypatch.setattr(settings, "public_base_url", "")
    user_id = uuid.uuid4()
    data = _png()

    first_url, first_path, first_size = _persist(user_id=user_id, data=data)
    second_url, second_path, second_size = _persist(user_id=user_id, data=data)

    assert first_url == second_url
    assert first_path == second_path
    assert first_size == second_size == len(data)
    assert first_path.read_bytes() == data
    assert first_path.name == f"{hashlib.sha256(data).hexdigest()}.png"
    assert str(user_id) in first_path.parts
    assert ReferenceStaticStorage.local_url_exists(first_url)


def test_reference_public_url_uses_product_origin_in_production(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "refs"))
    monkeypatch.setenv("REFERENCE_STATIC_PUBLIC_PREFIX", "/uploads/refs")
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example/")

    url, path, _size = _persist(user_id=uuid.uuid4(), data=_png())

    assert url.startswith("https://roxy.example/uploads/refs/image/")
    assert ReferenceStaticStorage.path_for_url(url) == path
    assert ReferenceStaticStorage.is_local_url(url)


def test_reference_path_resolution_rejects_traversal(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "refs"))
    monkeypatch.setenv("REFERENCE_STATIC_PUBLIC_PREFIX", "/uploads/refs")

    assert ReferenceStaticStorage.path_for_url("/uploads/refs/../secret") is None
    assert ReferenceStaticStorage.path_for_url("/uploads/refs/image/../../secret") is None
    assert not ReferenceStaticStorage.local_url_exists("/uploads/refs/../secret")
