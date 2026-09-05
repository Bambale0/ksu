import uuid
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.api.v1.generations import get_generation
from app.api.v1.media import public_media_asset, signed_media_asset
from app.core.config import settings
from app.db.media_models import MediaAsset, MediaIngestJob
from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.services.local_media_storage import (
    LOCAL_MEDIA_BUCKET,
    LocalMediaStorage,
    LocalMediaStorageError,
)
from app.services.media_assets import DownloadedMedia, MediaAssetService, MediaIngestService


def _telegram_id() -> int:
    return 8_800_000_000_000 + (uuid.uuid4().int % 999_999_999)


def test_local_media_storage_is_private_atomic_and_traversal_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "owned-media"
    monkeypatch.setenv("MEDIA_LOCAL_ROOT", str(root))
    source = tmp_path / "provider-result.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\nserver-owned")

    target = LocalMediaStorage.persist_file(
        source,
        key="generations/user/generation/000-deadbeef.png",
    )

    assert target.read_bytes() == source.read_bytes()
    assert target.is_relative_to(root.resolve())
    with pytest.raises(LocalMediaStorageError):
        LocalMediaStorage.path_for_key("../outside.png")
    with pytest.raises(LocalMediaStorageError):
        LocalMediaStorage.path_for_key("/absolute.png")


@pytest.mark.asyncio
async def test_media_ingest_persists_on_host_without_s3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIA_LOCAL_ROOT", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "s3_bucket", "")
    provider_file = tmp_path / "downloaded.png"
    provider_file.write_bytes(b"\x89PNG\r\n\x1a\nowned-result")

    async def fake_download(_cls: type[MediaIngestService], _url: str) -> DownloadedMedia:
        return DownloadedMedia(
            path=provider_file,
            size_bytes=provider_file.stat().st_size,
            sha256="a" * 64,
            content_type="image/png",
            suffix=".png",
        )

    monkeypatch.setattr(MediaIngestService, "_download", classmethod(fake_download))

    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Local")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="succeeded",
            prompt="host local",
            result_url="https://provider.example.invalid/result.png",
            cost_rox=Decimal("8"),
            provider="kie",
            parameters={"_model_id": "nano-banana"},
        )
        session.add(generation)
        await session.flush()
        asset = MediaAsset(
            generation_id=generation.id,
            user_id=user.id,
            ordinal=0,
            source_url=generation.result_url or "",
            status="pending",
        )
        session.add(asset)
        await session.flush()
        session.add(MediaIngestJob(asset_id=asset.id, status="pending", attempts=0))
        await session.commit()

        assert await MediaIngestService.process_one(session) is True
        await session.refresh(asset)
        assert asset.status == "ready"
        assert asset.bucket == LOCAL_MEDIA_BUCKET
        assert asset.object_key is not None
        assert LocalMediaStorage.path_for_key(asset.object_key).is_file()
        assert asset.sha256 == "a" * 64


@pytest.mark.asyncio
async def test_generation_detail_prefers_signed_host_media_without_s3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "s3_bucket", "")
    monkeypatch.setattr(settings, "admin_security_key", "m" * 48)

    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Signed")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="succeeded",
            prompt="signed local",
            result_url="https://provider.example.invalid/transient.png",
            cost_rox=Decimal("8"),
            provider="kie",
            parameters={
                "_model_id": "nano-banana",
                "_result_urls": ["https://provider.example.invalid/transient.png"],
            },
        )
        session.add(generation)
        await session.flush()
        asset = MediaAsset(
            generation_id=generation.id,
            user_id=user.id,
            ordinal=0,
            source_url=generation.result_url or "",
            status="ready",
            bucket=LOCAL_MEDIA_BUCKET,
            object_key=f"generations/{user.id}/{generation.id}/000-owned.png",
            content_type="image/png",
            size_bytes=123,
            sha256="b" * 64,
        )
        session.add(asset)
        await session.commit()

        detail = await get_generation(generation.id, user, session)
        assert detail["result_storage"] == "owned"
        assert len(detail["media"]) == 1
        result_url = str(detail["result_url"])
        assert result_url.startswith(f"/api/v1/media/{asset.id}/signed/")
        assert "provider.example.invalid" not in result_url
        assert detail["media"][0]["download_url"].endswith(f"/{asset.id}/download")


@pytest.mark.asyncio
async def test_signed_local_view_serves_private_file_but_public_route_stays_gated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIA_LOCAL_ROOT", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "admin_security_key", "s" * 48)

    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Private")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="succeeded",
            prompt="private local",
            result_url="https://provider.example.invalid/private.png",
            cost_rox=Decimal("8"),
            provider="kie",
            parameters={"_model_id": "nano-banana"},
        )
        session.add(generation)
        await session.flush()
        key = f"generations/{user.id}/{generation.id}/000-private.png"
        source = tmp_path / "private.png"
        source.write_bytes(b"\x89PNG\r\n\x1a\nprivate")
        LocalMediaStorage.persist_file(source, key=key)
        asset = MediaAsset(
            generation_id=generation.id,
            user_id=user.id,
            ordinal=0,
            source_url=generation.result_url or "",
            status="ready",
            bucket=LOCAL_MEDIA_BUCKET,
            object_key=key,
            content_type="image/png",
            size_bytes=source.stat().st_size,
            sha256="c" * 64,
        )
        session.add(asset)
        await session.commit()

        signed_url = LocalMediaStorage.signed_view_url(asset_id=asset.id, key=key)
        parts = urlparse(signed_url).path.strip("/").split("/")
        expires = int(parts[-2])
        signature = parts[-1]
        response = await signed_media_asset(asset.id, expires, signature, session)
        assert isinstance(response, FileResponse)

        with pytest.raises(HTTPException) as invalid:
            await signed_media_asset(asset.id, expires, "0" * 64, session)
        assert invalid.value.status_code == 404

        with pytest.raises(HTTPException) as unpublished:
            await public_media_asset(asset.id, session)
        assert unpublished.value.status_code == 404


def test_local_media_public_view_uses_server_route_for_published_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "admin_security_key", "p" * 48)
    generation_id = uuid.uuid4()
    asset = MediaAsset(
        id=uuid.uuid4(),
        generation_id=generation_id,
        user_id=uuid.uuid4(),
        ordinal=0,
        source_url="https://provider.example.invalid/result.png",
        status="ready",
        bucket=LOCAL_MEDIA_BUCKET,
        object_key=f"generations/user/{generation_id}/000-owned.png",
        content_type="image/png",
        size_bytes=123,
        sha256="d" * 64,
    )
    private_view = MediaAssetService.public_view(asset)
    public_view = MediaAssetService.public_view(asset, server_route=True)
    assert "/signed/" in str(private_view["url"])
    assert public_view["url"] == f"/api/v1/media/{asset.id}/public"
