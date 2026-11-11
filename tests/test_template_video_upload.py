"""Persisted Kling 4 template video uploads must not become personal media."""
from __future__ import annotations

import random
import uuid
from io import BytesIO
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.datastructures import Headers, UploadFile

from app.api.v1.uploads import upload_template_video
from app.db.models import AdminAccount, User
from app.db.reference_models import TemplateVideoReference, UserReference
from app.db.session import SessionFactory
from app.services.abuse_protection import AbuseProtectionService
from app.services.media_probe import MediaProbe
from app.services.reference_static import ReferenceStaticStorage
from app.services.template_video import TemplateVideoService


def upload(data: bytes = b"verified-video", *, mime: str = "video/mp4") -> UploadFile:
    return UploadFile(
        BytesIO(data), filename="motion.mp4",
        headers=Headers({"content-type": mime}),
    )


@pytest.mark.asyncio
async def test_pinned_video_upload_rejects_non_admin_before_storage(monkeypatch):
    persist = Mock()
    monkeypatch.setattr(ReferenceStaticStorage, "persist_stream", persist)
    async with SessionFactory() as session:
        owner = User(telegram_id=random.randrange(8_000_000_000_000, 8_999_999_999_999))
        session.add(owner)
        await session.commit()
        with pytest.raises(HTTPException) as error:
            await upload_template_video(owner, AsyncMock(), session, upload())
        assert error.value.status_code == 403
        persist.assert_not_called()


@pytest.mark.asyncio
async def test_admin_upload_pins_verified_video_outside_personal_reference_lifetime(monkeypatch, tmp_path):
    monkeypatch.setattr(AbuseProtectionService, "upload_rate_and_bytes", AsyncMock())
    monkeypatch.setattr(
        "app.api.v1.uploads.probe_media_stream",
        lambda *_: MediaProbe(status="ready", duration_ms=5000, has_video=True, video_codec="h264"),
    )
    monkeypatch.setattr(
        ReferenceStaticStorage, "persist_stream",
        lambda *args, **kwargs: (
            f"/uploads/refs/video/{kwargs['user_id']}/motion.mp4",
            tmp_path / "motion.mp4", len(b"verified-video"),
        ),
    )
    monkeypatch.setattr(ReferenceStaticStorage, "local_url_exists", lambda _: True)
    async with SessionFactory() as session:
        owner = User(telegram_id=random.randrange(8_000_000_000_000, 8_999_999_999_999))
        session.add(owner)
        await session.flush()
        session.add(AdminAccount(user_id=owner.id, role="admin"))
        await session.commit()

        result = await upload_template_video(owner, AsyncMock(), session, upload())
        assert result["reference"]["kind"] == "video"
        assert result["probe_status"] == "ready"
        assert result["duration_ms"] == 5000
        row = await session.scalar(select(TemplateVideoReference).where(
            TemplateVideoReference.source_url == result["url"],
        ))
        assert row is not None and row.status == "ready"
        assert await session.scalar(select(UserReference.id).where(
            UserReference.source_url == result["url"],
        )) is None
        assert await TemplateVideoService.verified(session, result["url"]) is row
        with TemplateVideoService.authorized(session, result["url"]):
            assert await TemplateVideoService.authorized_reference(session, result["url"]) is row
        assert await TemplateVideoService.authorized_reference(session, result["url"]) is None

        await session.delete(owner)
        await session.commit()
        await session.refresh(row)
        assert row.uploaded_by is None
        assert await TemplateVideoService.verified(session, result["url"]) is row


@pytest.mark.asyncio
@pytest.mark.parametrize("mime,probe,expected", [
    ("image/png", None, 415),
    ("video/webm", None, 415),
    ("video/mp4", {"status": "failed", "has_video": True}, 422),
    ("video/mp4", {"status": "ready", "has_video": False, "duration_ms": 5000}, 422),
    ("video/mp4", {"status": "ready", "has_video": True, "duration_ms": 1000}, 422),
    ("video/mp4", {"status": "ready", "has_video": True, "duration_ms": 31000}, 422),
])
async def test_pinned_upload_rejects_disallowed_media_before_persistence(monkeypatch, mime, probe, expected):
    monkeypatch.setattr("app.api.v1.trends._inline_admin", AsyncMock())
    monkeypatch.setattr(AbuseProtectionService, "upload_rate_and_bytes", AsyncMock())
    monkeypatch.setattr(
        "app.api.v1.uploads.probe_media_stream",
        lambda *_: MediaProbe(**(probe or {"status": "failed"})),
    )
    persist = Mock()
    monkeypatch.setattr(ReferenceStaticStorage, "persist_stream", persist)
    with pytest.raises(HTTPException) as error:
        await upload_template_video(
            User(id=uuid.uuid4()), AsyncMock(), AsyncMock(),
            upload(mime=mime),
        )
    assert error.value.status_code == expected
    persist.assert_not_called()


@pytest.mark.asyncio
async def test_pinned_upload_honors_kling_provider_size_limit(monkeypatch):
    monkeypatch.setattr("app.api.v1.trends._inline_admin", AsyncMock())
    monkeypatch.setattr("app.api.v1.uploads._upload_size", lambda *_: 11 * 1024 * 1024)
    persist = Mock()
    monkeypatch.setattr(ReferenceStaticStorage, "persist_stream", persist)
    with pytest.raises(HTTPException) as error:
        await upload_template_video(User(id=uuid.uuid4()), AsyncMock(), AsyncMock(), upload())
    assert error.value.status_code == 413
    persist.assert_not_called()
