from __future__ import annotations

import uuid
from io import BytesIO
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import select
from starlette.datastructures import Headers, UploadFile

from app.api.v1 import trends as trends_api
from app.api.v1.uploads import upload_template_image
from app.db.models import AdminAccount, User
from app.db.reference_models import TemplateImageReference, UserReference
from app.db.session import SessionFactory
from app.services.abuse_protection import AbuseProtectionService
from app.services.reference_static import ReferenceStaticStorage


def upload(data: bytes | None = None) -> UploadFile:
    if data is None:
        buffer = BytesIO()
        Image.new("RGB", (40, 50), "blue").save(buffer, "PNG")
        data = buffer.getvalue()
    return UploadFile(
        BytesIO(data), filename="outfit.png", headers=Headers({"content-type": "image/png"})
    )


@pytest.mark.asyncio
async def test_non_admin_cannot_store_preset_image(monkeypatch):
    persist = Mock()
    monkeypatch.setattr(ReferenceStaticStorage, "persist_stream", persist)
    monkeypatch.setattr(trends_api, "_inline_admin", AsyncMock(side_effect=HTTPException(403)))
    with pytest.raises(HTTPException) as error:
        await upload_template_image(User(id=uuid.uuid4()), AsyncMock(), AsyncMock(), upload())
    assert error.value.status_code == 403
    persist.assert_not_called()


@pytest.mark.asyncio
async def test_mime_disguised_video_cannot_be_saved_as_preset_photo(monkeypatch):
    monkeypatch.setattr(trends_api, "_inline_admin", AsyncMock())
    monkeypatch.setattr(AbuseProtectionService, "upload_rate_and_bytes", AsyncMock())
    persist = Mock()
    monkeypatch.setattr(ReferenceStaticStorage, "persist_stream", persist)
    with pytest.raises(HTTPException) as error:
        await upload_template_image(
            User(id=uuid.uuid4()), AsyncMock(), AsyncMock(), upload(b"fake image bytes")
        )
    assert error.value.status_code == 422
    persist.assert_not_called()


@pytest.mark.asyncio
async def test_truncated_jpeg_cannot_be_saved_as_verified_preset(monkeypatch):
    monkeypatch.setattr(trends_api, "_inline_admin", AsyncMock())
    monkeypatch.setattr(AbuseProtectionService, "upload_rate_and_bytes", AsyncMock())
    buffer = BytesIO()
    Image.new("RGB", (300, 300), "blue").save(buffer, "JPEG")
    broken = buffer.getvalue()[: len(buffer.getvalue()) // 2]
    file = UploadFile(
        BytesIO(broken), filename="truncated.jpg", headers=Headers({"content-type": "image/jpeg"})
    )
    persist = Mock(return_value=("https://roxy.example/fake.jpg", "unused", len(broken)))
    monkeypatch.setattr(ReferenceStaticStorage, "persist_stream", persist)
    session = AsyncMock()
    session.add = Mock()
    with pytest.raises(HTTPException) as error:
        await upload_template_image(User(id=uuid.uuid4()), AsyncMock(), session, file)
    assert error.value.status_code == 422
    persist.assert_not_called()


@pytest.mark.asyncio
async def test_preset_image_remains_after_uploader_deletion_and_outside_personal_memory(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(AbuseProtectionService, "upload_rate_and_bytes", AsyncMock())
    monkeypatch.setattr(
        ReferenceStaticStorage,
        "persist_stream",
        lambda *args, **kwargs: (
            f"https://roxy.example/uploads/refs/image/{kwargs['user_id']}/image.png",
            tmp_path / "image.png",
            100,
        ),
    )
    async with SessionFactory() as session:
        owner = User(telegram_id=uuid.uuid4().int % 10**14)
        session.add(owner)
        await session.flush()
        session.add(AdminAccount(user_id=owner.id, role="admin"))
        await session.commit()
        result = await upload_template_image(owner, AsyncMock(), session, upload())
        row = await session.scalar(
            select(TemplateImageReference).where(TemplateImageReference.source_url == result["url"])
        )
        assert row is not None and row.width == 40 and row.height == 50
        assert (
            await session.scalar(
                select(UserReference.id).where(UserReference.source_url == result["url"])
            )
            is None
        )
        await session.delete(owner)
        await session.commit()
        await session.refresh(row)
        assert row.uploaded_by is None and row.status == "ready"
