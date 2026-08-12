import random
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.v1.generations import get_generation
from app.api.v1.media import get_media_asset
from app.core.config import settings
from app.db.media_models import MediaAsset, MediaIngestJob
from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.providers.kie import KieTask
from app.services.generation_provider import GenerationProviderService
from app.services.media_assets import MediaAssetService, MediaIngestService, UnsafeMediaSource


def _telegram_id(prefix: int) -> int:
    return prefix * 1_000_000_000_000 + random.randint(1, 999_999_999)


@pytest.mark.asyncio
async def test_successful_generation_enqueues_media_idempotently() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(61), first_name="Media")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="generating",
            prompt="owned media",
            cost_rox=Decimal("8"),
            provider="kie",
            external_id="media-task",
            parameters={"_model_id": "nano-banana"},
        )
        session.add(generation)
        await session.commit()

        task = KieTask(
            task_id="media-task",
            state="success",
            result_urls=[
                "https://cdn.example.invalid/result-1.png",
                "https://cdn.example.invalid/result-2.png",
            ],
        )
        await GenerationProviderService.apply_kie_task(session, generation, task)
        await GenerationProviderService.apply_kie_task(session, generation, task)

        asset_count = int(
            await session.scalar(
                select(func.count()).select_from(MediaAsset).where(
                    MediaAsset.generation_id == generation.id
                )
            )
            or 0
        )
        job_count = int(
            await session.scalar(
                select(func.count())
                .select_from(MediaIngestJob)
                .join(MediaAsset, MediaAsset.id == MediaIngestJob.asset_id)
                .where(MediaAsset.generation_id == generation.id)
            )
            or 0
        )
        assert asset_count == 2
        assert job_count == 2
        refreshed = await session.get(Generation, generation.id)
        assert refreshed is not None
        assert refreshed.status == "succeeded"


@pytest.mark.asyncio
async def test_generation_detail_prefers_owned_presigned_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "s3_bucket", "ksu-test-media")
    monkeypatch.setattr(settings, "s3_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_endpoint_url", "")
    monkeypatch.setattr(settings, "s3_access_key_id", "test-access")
    monkeypatch.setattr(settings, "s3_secret_access_key", "test-secret")
    monkeypatch.setattr(settings, "s3_session_token", "")
    monkeypatch.setattr(settings, "s3_addressing_style", "virtual")

    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(62), first_name="Owned")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="succeeded",
            prompt="prefer s3",
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
            bucket="ksu-test-media",
            object_key=f"generations/{user.id}/{generation.id}/000-test.png",
            content_type="image/png",
            size_bytes=123,
            sha256="a" * 64,
        )
        session.add(asset)
        await session.commit()

        detail = await get_generation(generation.id, user, session)
        assert detail["result_storage"] == "owned"
        assert len(detail["media"]) == 1
        assert detail["result_urls"] == [detail["media"][0]["url"]]
        assert "provider.example.invalid" not in str(detail["result_url"])
        assert "X-Amz-Signature" in str(detail["result_url"])
        assert detail["media"][0]["download_url"].endswith(f"/{asset.id}/download")


@pytest.mark.asyncio
async def test_media_metadata_is_owner_scoped() -> None:
    async with SessionFactory() as session:
        owner = User(telegram_id=_telegram_id(63), first_name="Owner")
        other = User(telegram_id=_telegram_id(64), first_name="Other")
        session.add_all([owner, other])
        await session.flush()
        generation = Generation(
            user_id=owner.id,
            kind="text_to_image",
            status="succeeded",
            prompt="private asset",
            result_url="https://provider.example.invalid/private.png",
            cost_rox=Decimal("8"),
            provider="kie",
            parameters={"_model_id": "nano-banana"},
        )
        session.add(generation)
        await session.flush()
        asset = MediaAsset(
            generation_id=generation.id,
            user_id=owner.id,
            ordinal=0,
            source_url=generation.result_url or "",
            status="pending",
        )
        session.add(asset)
        await session.commit()

        own = await get_media_asset(asset.id, owner, session)
        assert own["id"] == str(asset.id)
        with pytest.raises(HTTPException) as exc_info:
            await get_media_asset(asset.id, other, session)
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_media_source_rejects_private_and_plain_http() -> None:
    with pytest.raises(UnsafeMediaSource):
        await MediaIngestService._validate_public_https_url("https://127.0.0.1/private.png")
    with pytest.raises(UnsafeMediaSource):
        await MediaIngestService._validate_public_https_url("http://8.8.8.8/public.png")
    await MediaIngestService._validate_public_https_url("https://8.8.8.8/public.png")


@pytest.mark.asyncio
async def test_legacy_success_can_be_repaired_into_ingest_queue() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(65), first_name="Legacy")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="succeeded",
            prompt="legacy",
            result_url="https://legacy.example.invalid/result.png",
            cost_rox=Decimal("8"),
            provider="kie",
            parameters={
                "_model_id": "nano-banana",
                "_result_urls": ["https://legacy.example.invalid/result.png"],
            },
        )
        session.add(generation)
        await session.commit()

        created = await MediaAssetService.ensure_legacy(session, limit=100)
        asset = await session.scalar(
            select(MediaAsset).where(MediaAsset.generation_id == generation.id)
        )
        assert created >= 1
        assert asset is not None
        assert await session.get(MediaIngestJob, asset.id) is not None


def test_media_storage_docs_cover_bucket_lifecycle_and_worker() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    doc = (root / "docs" / "MEDIA_STORAGE.md").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    for token in (
        "AbortIncompleteMultipartUpload",
        "Access-Control-Allow-Origin: https://web.telegram.org",
        "FOR UPDATE SKIP LOCKED",
        "MEDIA_INGEST_MAX_BYTES",
        "/api/v1/media/{asset_id}/download",
    ):
        assert token in doc, token
    assert "media-worker" in compose
