from __future__ import annotations

import random
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.v1.generation_actions import DeriveGenerationRequest, derive_generation
from app.db.models import Generation, User
from app.db.session import SessionFactory


def _telegram_id() -> int:
    return random.randint(7_100_000_000_000, 7_999_999_999_999)


@pytest.mark.asyncio
async def test_repeat_cannot_switch_image_parent_to_video_model() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Boundary")
        session.add(user)
        await session.flush()
        parent = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="succeeded",
            prompt="portrait",
            result_url="https://cdn.example/parent.png",
            cost_rox=Decimal("25.00"),
            provider="kie",
            parameters={"_model_id": "nano-banana-pro", "_media_type": "image"},
        )
        session.add(parent)
        await session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await derive_generation(
                parent.id,
                "repeat",
                DeriveGenerationRequest(
                    model_id="grok-video-i2v",
                    prompt="portrait",
                    parameters={},
                ),
                user,
                session,
                object(),  # type: ignore[arg-type]
            )

        assert exc_info.value.status_code == 422
        assert "not compatible" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_remix_rejects_text_only_image_model() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Boundary")
        session.add(user)
        await session.flush()
        parent = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="succeeded",
            prompt="portrait",
            result_url="https://cdn.example/parent.png",
            cost_rox=Decimal("25.00"),
            provider="kie",
            parameters={"_model_id": "nano-banana-pro", "_media_type": "image"},
        )
        session.add(parent)
        await session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await derive_generation(
                parent.id,
                "remix",
                DeriveGenerationRequest(
                    model_id="gpt-image-2-t2i",
                    prompt="make it blue",
                    parameters={},
                ),
                user,
                session,
                object(),  # type: ignore[arg-type]
            )

        assert exc_info.value.status_code == 422
        assert "not compatible" in str(exc_info.value.detail)
