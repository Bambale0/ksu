from __future__ import annotations

import io
import hashlib
import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from PIL import Image

from app.api.v1.trends import trend_preview_thumbnail
from app.services.reference_static import ReferenceStaticStorage


@pytest.mark.asyncio
async def test_active_stored_trend_has_small_cacheable_thumbnail(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "refs"))
    monkeypatch.setenv("REFERENCE_STATIC_PUBLIC_PREFIX", "/uploads/refs")
    buffer = io.BytesIO()
    Image.new("RGB", (900, 700), (80, 100, 130)).save(buffer, "PNG")
    data = buffer.getvalue()
    url, _path, _size = ReferenceStaticStorage.persist_stream(
        io.BytesIO(data), user_id=uuid.uuid4(), kind="image", file_hash=hashlib.sha256(data).hexdigest(),
        filename="reference.png", content_type="image/png", expected_size=len(data),
    )
    trend_id = uuid.uuid4()
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(id=trend_id, is_active=True, payload={"preview_url": url})

    response = await trend_preview_thumbnail(trend_id, session)
    assert response.status_code == 202
    assert response.headers["Retry-After"] == "1"
    for _ in range(30):
        await asyncio.sleep(0.05)
        response = await trend_preview_thumbnail(trend_id, session)
        if response.status_code == 200:
            break

    assert response.media_type == "image/webp"
    assert response.headers["Cache-Control"].startswith("public, max-age=")
    with Image.open(Path(response.path)) as image:
        assert max(image.size) <= 320
    session.get.return_value.is_active = False
    with pytest.raises(HTTPException) as exc:
        await trend_preview_thumbnail(trend_id, session)
    assert exc.value.status_code == 404
