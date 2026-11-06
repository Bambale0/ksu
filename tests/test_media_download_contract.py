from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user
from app.api.v1.generations import get_generation
from app.api.v1.media import router
from app.core.config import settings
from app.db.media_models import MediaAsset
from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.services.local_media_storage import LOCAL_MEDIA_BUCKET, LocalMediaStorage
from app.services.media_assets import MediaAssetService

CONTENTS = b"\x89PNG\r\n\x1a\nsynthetic-owned-download"


@pytest.fixture
async def owned_media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[User, User, MediaAsset]:
    monkeypatch.setenv("MEDIA_LOCAL_ROOT", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "admin_security_key", "synthetic-download-signing-key-00000000")
    monkeypatch.setattr(settings, "bot_token", "synthetic-test-only")
    async with SessionFactory() as session:
        owner, other = [
            User(telegram_id=uuid.uuid4().int % 10**14, first_name="Synthetic download user")
            for _ in range(2)
        ]
        session.add_all([owner, other])
        await session.flush()
        generation = Generation(
            user_id=owner.id, kind="text_to_image", status="succeeded",
            prompt="Synthetic private download", provider="kie", cost_rox=Decimal("0"),
            result_url="https://provider.invalid/result.png",
            parameters={"_model_id": "nano-banana"},
        )
        session.add(generation)
        await session.flush()
        asset = MediaAsset(
            generation_id=generation.id, user_id=owner.id, ordinal=0,
            source_url=generation.result_url, status="ready",
            bucket=LOCAL_MEDIA_BUCKET,
            object_key=f"generations/{owner.id}/{generation.id}/000-result.png",
            content_type="image/png", size_bytes=len(CONTENTS), sha256="a" * 64,
        )
        source = tmp_path / "result.png"
        source.write_bytes(CONTENTS)
        LocalMediaStorage.persist_file(source, key=asset.object_key)
        session.add(asset)
        await session.commit()
        return owner, other, asset


@pytest.fixture
async def media_client() -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://roxy.test",
    ) as client:
        yield app, client


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["asset_metadata", "generation_detail"])
async def test_owner_download_descriptor_works_as_ordinary_browser_navigation(
    owned_media, media_client, source: str,
) -> None:
    owner, _other, asset = owned_media
    app, client = media_client

    async def owner_context():
        return owner

    app.dependency_overrides[get_current_user] = owner_context
    if source == "asset_metadata":
        response = await client.get(f"/api/v1/media/{asset.id}")
        assert response.status_code == 200, response.text
        descriptor = response.json()
    else:
        async with SessionFactory() as session:
            descriptor = (await get_generation(asset.generation_id, owner, session))["media"][0]
    app.dependency_overrides.clear()

    # A real link/Telegram download request has no Mini App authentication header.
    response = await client.get(descriptor["download_url"])
    assert response.status_code == 200, response.text
    filename = f"generation-{asset.generation_id}-1.png"
    assert response.content == CONTENTS
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"] == f'attachment; filename="{filename}"'
    assert response.headers["access-control-allow-origin"] == "https://web.telegram.org"
    assert descriptor["download_filename"] == filename
    assert "initData" not in descriptor["download_url"]
    assert "synthetic-test-only" not in descriptor["download_url"]


@pytest.mark.asyncio
async def test_download_metadata_stays_owner_scoped_and_unsigned_route_requires_auth(
    owned_media, media_client,
) -> None:
    _owner, other, asset = owned_media
    app, client = media_client

    async def other_context():
        return other

    app.dependency_overrides[get_current_user] = other_context
    response = await client.get(f"/api/v1/media/{asset.id}")
    assert response.status_code == 404
    response = await client.get(f"/api/v1/media/{asset.id}/download")
    assert response.status_code == 404
    app.dependency_overrides.clear()
    response = await client.get(f"/api/v1/media/{asset.id}/download")
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["signature", "expiry", "asset_id"])
async def test_signed_download_rejects_tampering_and_expiry(
    owned_media, media_client, monkeypatch: pytest.MonkeyPatch, tamper: str,
) -> None:
    _owner, _other, asset = owned_media
    _app, client = media_client
    descriptor = MediaAssetService.public_view(asset)
    link = str(descriptor["download_url"])
    assert "/signed/" in link
    parts = urlsplit(link).path.split("/")
    if tamper == "signature":
        link = link.replace(parts[-1], "0" * 64)
    elif tamper == "expiry":
        monkeypatch.setattr("app.services.local_media_storage.time.time", lambda: int(parts[-2]) + 1)
    else:
        link = link.replace(str(asset.id), str(uuid.uuid4()))
    response = await client.get(link)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_private_view_and_publication_gates_do_not_change_for_downloads(
    owned_media, media_client,
) -> None:
    _owner, _other, asset = owned_media
    _app, client = media_client
    descriptor = MediaAssetService.public_view(asset)
    view = await client.get(str(descriptor["url"]))
    assert view.status_code == 200
    assert view.content == CONTENTS
    assert "content-disposition" not in view.headers
    public = await client.get(f"/api/v1/media/{asset.id}/public")
    assert public.status_code == 404
    public_descriptor = MediaAssetService.public_view(asset, server_route=True)
    assert "/signed/" not in str(public_descriptor["download_url"])


@pytest.mark.asyncio
async def test_signed_download_is_bound_to_the_stored_object_key(owned_media, media_client) -> None:
    _owner, _other, asset = owned_media
    _app, client = media_client
    link = str(MediaAssetService.public_view(asset)["download_url"])
    async with SessionFactory() as session:
        stored = await session.get(MediaAsset, asset.id)
        stored.object_key = str(stored.object_key).replace("000-result", "001-replaced")
        await session.commit()
    response = await client.get(link)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_video_download_streams_the_original_file_and_supports_byte_ranges(
    owned_media, media_client, tmp_path: Path,
) -> None:
    _owner, _other, asset = owned_media
    _app, client = media_client
    contents = (Path(__file__).parent / "fixtures" / "feed-playback.mp4").read_bytes()
    source = tmp_path / "fixture.mp4"
    source.write_bytes(contents)
    key = str(asset.object_key).replace(".png", ".mp4")
    LocalMediaStorage.persist_file(source, key=key)
    async with SessionFactory() as session:
        stored = await session.get(MediaAsset, asset.id)
        stored.object_key = key
        stored.content_type = "video/mp4"
        stored.size_bytes = len(contents)
        await session.commit()
        descriptor = MediaAssetService.public_view(stored)
    full = await client.get(str(descriptor["download_url"]))
    assert full.status_code == 200
    assert full.content == contents
    assert full.headers["content-type"] == "video/mp4"
    assert full.headers["content-disposition"].endswith('-1.mp4"')
    partial = await client.get(
        str(descriptor["download_url"]), headers={"Range": "bytes=0-15"},
    )
    assert partial.status_code == 206
    assert partial.content == contents[:16]
    assert partial.headers["content-range"] == f"bytes 0-15/{len(contents)}"
    assert partial.headers["content-disposition"] == full.headers["content-disposition"]
