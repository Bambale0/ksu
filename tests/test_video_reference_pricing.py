from __future__ import annotations

import random
from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.models import User
from app.db.reference_models import UserReference
from app.db.session import SessionFactory
from app.services.generations import GenerationService


def _seedance_params() -> dict[str, object]:
    return {
        "duration": 5,
        "resolution": "720p",
        "aspect_ratio": "adaptive",
        "output_format": "mp4",
        "generate_audio": False,
        "return_last_frame": False,
        "web_search": False,
        "nsfw_checker": True,
    }


async def _trusted_reference(
    session,
    *,
    kind: str,
    url: str,
    duration_ms: int | None = None,
) -> None:
    user = User(
        telegram_id=random.randint(9_810_000_000_000, 9_819_999_999_999),
        first_name="Video pricing",
    )
    session.add(user)
    await session.flush()
    session.add(
        UserReference(
            user_id=user.id,
            kind=kind,
            status="ready",
            source_url=url,
            source="mini_app_upload",
            size_bytes=1024,
            duration_ms=duration_ms,
            probe_status="ready",
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_video_reference_doubles_authoritative_generation_price() -> None:
    previous = settings.generation_pricing_json
    settings.generation_pricing_json = '{"seedance-2.5":{"per_second":10}}'
    video_url = "https://cdn.example/motion.mp4"
    try:
        async with SessionFactory() as session:
            await _trusted_reference(session, kind="video", url=video_url, duration_ms=5000)
            spec, clean, cost, seconds, unit_price = await GenerationService.prepare_request(
                session,
                model_id="seedance-2.5",
                prompt="follow this motion reference",
                parameters={
                    **_seedance_params(),
                    "reference_video_urls": [video_url],
                },
            )
    finally:
        settings.generation_pricing_json = previous

    assert spec.id == "seedance-2.5"
    assert clean["reference_video_urls"] == [video_url]
    assert seconds == 5
    assert unit_price == Decimal("20")
    assert cost == Decimal("100.00")


@pytest.mark.asyncio
async def test_image_reference_keeps_normal_generation_price() -> None:
    previous = settings.generation_pricing_json
    settings.generation_pricing_json = '{"seedance-2.5":{"per_second":10}}'
    image_url = "https://cdn.example/subject.png"
    try:
        async with SessionFactory() as session:
            await _trusted_reference(session, kind="image", url=image_url)
            _spec, clean, cost, seconds, unit_price = await GenerationService.prepare_request(
                session,
                model_id="seedance-2.5",
                prompt="keep this character consistent",
                parameters={
                    **_seedance_params(),
                    "reference_image_urls": [image_url],
                },
            )
    finally:
        settings.generation_pricing_json = previous

    assert clean["reference_image_urls"] == [image_url]
    assert seconds == 5
    assert unit_price == Decimal("10")
    assert cost == Decimal("50.00")


@pytest.mark.asyncio
async def test_legacy_video_reference_alias_is_normalized_and_doubled() -> None:
    previous = settings.generation_pricing_json
    settings.generation_pricing_json = '{"seedance-2.5":{"per_second":10}}'
    video_url = "https://cdn.example/legacy-motion.mp4"
    try:
        async with SessionFactory() as session:
            await _trusted_reference(session, kind="video", url=video_url, duration_ms=5000)
            _spec, clean, cost, seconds, unit_price = await GenerationService.prepare_request(
                session,
                model_id="seedance-2.5",
                prompt="use legacy motion reference",
                parameters={
                    **_seedance_params(),
                    "video_reference_urls": [video_url],
                },
            )
    finally:
        settings.generation_pricing_json = previous

    assert clean["reference_video_urls"] == [video_url]
    assert seconds == 5
    assert unit_price == Decimal("20")
    assert cost == Decimal("100.00")
