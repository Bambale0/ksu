from __future__ import annotations

import random
import uuid
from decimal import Decimal

import pytest

from app.db.models import Generation, User
from app.db.reference_models import UserReference
from app.db.session import SessionFactory
from app.services.generations import GenerationService
from app.services.model_catalog import InvalidModelParametersError, ModelCatalog
from app.services.model_spec_trusted_media_audit import validate_owned_trusted_sources
from app.services.model_ui_contract import build_public_model_ui_schema


async def _user(session) -> User:  # type: ignore[no-untyped-def]
    row = User(
        telegram_id=random.randint(12_100_000_000_000, 12_999_999_999_999),
        first_name="Trusted billing",
    )
    session.add(row)
    await session.flush()
    return row


async def _trusted_reference(
    session,  # type: ignore[no-untyped-def]
    *,
    user_id: uuid.UUID,
    kind: str,
    seconds: float,
    suffix: str,
) -> UserReference:
    row = UserReference(
        user_id=user_id,
        kind=kind,
        status="ready",
        source_url=f"https://cdn.example.invalid/{uuid.uuid4()}.{suffix}",
        source="mini_app_upload",
        size_bytes=1024,
        duration_ms=round(seconds * 1000),
        probe_status="ready",
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_avatar_billing_ignores_client_seconds_and_uses_audio_metadata() -> None:
    async with SessionFactory() as session:
        owner = await _user(session)
        audio = await _trusted_reference(
            session,
            user_id=owner.id,
            kind="audio",
            seconds=11.5,
            suffix="wav",
        )
        image = await _trusted_reference(
            session,
            user_id=owner.id,
            kind="image",
            seconds=1,
            suffix="png",
        )
        await session.commit()

        _spec, _clean, cost, seconds, unit = await GenerationService.prepare_request(
            session,
            model_id="kling-avatar-standard",
            prompt="",
            parameters={"image_url": image.source_url, "audio_url": audio.source_url},
            billing_seconds=1,
        )

        assert seconds == 12
        assert cost == (unit * Decimal(12)).quantize(Decimal("0.01"))


@pytest.mark.asyncio
async def test_motion_duration_cannot_be_underreported_to_bypass_orientation_limit() -> None:
    async with SessionFactory() as session:
        owner = await _user(session)
        image = await _trusted_reference(
            session,
            user_id=owner.id,
            kind="image",
            seconds=1,
            suffix="png",
        )
        motion = await _trusted_reference(
            session,
            user_id=owner.id,
            kind="video",
            seconds=12,
            suffix="mp4",
        )
        await session.commit()

        with pytest.raises(
            InvalidModelParametersError,
            match="image orientation supports motion videos up to 10 seconds",
        ):
            await GenerationService.prepare_request(
                session,
                model_id="kling-motion-3.0",
                prompt="Follow the motion",
                parameters={
                    "prompt": "Follow the motion",
                    "input_urls": [image.source_url],
                    "video_urls": [motion.source_url],
                    "mode": "720p",
                    "character_orientation": "image",
                    "background_source": "input_video",
                },
                billing_seconds=1,
            )

        _spec, _clean, _cost, seconds, _unit = await GenerationService.prepare_request(
            session,
            model_id="kling-motion-3.0",
            prompt="Follow the motion",
            parameters={
                "prompt": "Follow the motion",
                "input_urls": [image.source_url],
                "video_urls": [motion.source_url],
                "mode": "720p",
                "character_orientation": "video",
                "background_source": "input_video",
            },
            billing_seconds=1,
        )
        assert seconds == 12


@pytest.mark.asyncio
async def test_wan_video_edit_auto_bills_verified_source_duration() -> None:
    async with SessionFactory() as session:
        owner = await _user(session)
        video = await _trusted_reference(
            session,
            user_id=owner.id,
            kind="video",
            seconds=8.5,
            suffix="mp4",
        )
        await session.commit()

        _spec, _clean, cost, seconds, unit = await GenerationService.prepare_request(
            session,
            model_id="wan-2.7-video-edit",
            prompt="Clean this clip",
            parameters={
                "prompt": "Clean this clip",
                "video_url": video.source_url,
                "duration": 0,
                "resolution": "1080p",
                "audio_setting": "auto",
            },
            billing_seconds=1,
        )

        assert seconds == 9
        assert cost == (unit * Decimal(9)).quantize(Decimal("0.01"))


@pytest.mark.asyncio
async def test_gemini_video_bills_verified_selected_segment_not_ignored_duration() -> None:
    async with SessionFactory() as session:
        owner = await _user(session)
        video = await _trusted_reference(
            session,
            user_id=owner.id,
            kind="video",
            seconds=10,
            suffix="mp4",
        )
        await session.commit()

        _spec, clean, cost, seconds, unit = await GenerationService.prepare_request(
            session,
            model_id="gemini-omni-video",
            prompt="Transform this clip",
            parameters={
                "prompt": "Transform this clip",
                "video_list": [{"url": video.source_url, "start": 2, "ends": 9}],
                "duration": 4,
                "aspect_ratio": "16:9",
                "resolution": "720p",
            },
        )

        assert clean["duration"] == 4
        assert seconds == 7
        assert cost == (unit * Decimal(7)).quantize(Decimal("0.01"))


@pytest.mark.asyncio
async def test_grok_upscale_uses_source_task_duration_and_create_ownership_is_scoped() -> None:
    async with SessionFactory() as session:
        owner = await _user(session)
        other = await _user(session)
        task_id = f"grok_{uuid.uuid4().hex}"
        source = Generation(
            user_id=owner.id,
            kind="text_to_video",
            status="success",
            prompt="source",
            cost_rox=Decimal("1"),
            provider="kie",
            external_id=task_id,
            parameters={"_model_family": "grok", "_billing_seconds": 9},
        )
        session.add(source)
        await session.commit()

        _spec, _clean, _cost, seconds, _unit = await GenerationService.prepare_request(
            session,
            model_id="grok-video-upscale",
            prompt="",
            parameters={"task_id": task_id, "resolution": "1080p"},
            billing_seconds=1,
        )
        assert seconds == 9

        with pytest.raises(
            InvalidModelParametersError,
            match="Grok Upscale requires one of your completed Grok tasks",
        ):
            await validate_owned_trusted_sources(
                session,
                user_id=other.id,
                model_id="grok-video-upscale",
                parameters={"task_id": task_id},
            )

        await validate_owned_trusted_sources(
            session,
            user_id=owner.id,
            model_id="grok-video-upscale",
            parameters={"task_id": task_id},
        )


@pytest.mark.asyncio
async def test_unverified_duration_source_fails_closed() -> None:
    async with SessionFactory() as session:
        with pytest.raises(
            InvalidModelParametersError,
            match="duration must be verified: upload this media through ROXY",
        ):
            await GenerationService.prepare_request(
                session,
                model_id="kling-avatar-pro",
                prompt="",
                parameters={
                    "image_url": "https://cdn.example.invalid/avatar.png",
                    "audio_url": "https://cdn.example.invalid/speech.wav",
                },
                billing_seconds=1,
            )


def test_media_derived_models_do_not_expose_client_billing_seconds() -> None:
    for model_id in (
        "kling-avatar-standard",
        "kling-avatar-pro",
        "kling-motion-2.6",
        "kling-motion-3.0",
        "wan-2.7-video-edit",
    ):
        schema = build_public_model_ui_schema(ModelCatalog.get(model_id).public_dict())
        assert "billing_seconds" not in schema
        assert schema["billing_source"] == "reference_metadata"

    gemini = build_public_model_ui_schema(ModelCatalog.get("gemini-omni-video").public_dict())
    assert gemini["video_billing_source"] == "verified_video_segment"
