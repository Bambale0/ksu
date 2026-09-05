from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.api.v1.generation_action_contexts import create_context, read_context
from app.core.config import settings
from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.services.generation_action_contexts import (
    ActionContextExpiredError,
    ActionContextNotFoundError,
    build_action_context_payload,
    create_action_context,
    get_action_context,
    mark_action_context_executed,
)
from app.services.feed import FeedService


def _telegram_id() -> int:
    return random.randint(8_100_000_000_000, 8_999_999_999_999)


def _image_generation(user_id: uuid.UUID) -> Generation:
    return Generation(
        id=uuid.uuid4(),
        user_id=user_id,
        kind="text_to_image",
        status="succeeded",
        prompt="portrait in soft light",
        result_url="https://cdn.example/result.png",
        cost_rox=Decimal("25.00"),
        provider="kie",
        parameters={
            "_model_id": "nano-banana-pro",
            "_media_type": "image",
            "_model_title": "Nano Banana Pro",
        },
    )


async def _user(session, name: str = "Actions") -> User:
    user = User(telegram_id=_telegram_id(), first_name=name)
    session.add(user)
    await session.flush()
    return user


async def _resolved_context(session, user: User, generation: Generation):  # type: ignore[no-untyped-def]
    context = await create_action_context(
        session,
        user_id=user.id,
        generation=generation,
        action="remix",
    )
    await session.commit()
    return context


@pytest.mark.asyncio
async def test_created_context_snapshots_the_live_action_context_payload() -> None:
    async with SessionFactory() as session:
        user = await _user(session)
        generation = _image_generation(user.id)
        session.add(generation)
        await session.commit()

        context = await _resolved_context(session, user, generation)

        payload = dict(context.payload_json)
        live = build_action_context_payload(generation, "remix")
        assert payload == live
        assert context.action == "remix"
        assert context.source_generation_id == generation.id
        assert context.user_id == user.id
        assert context.target_mode == "image_to_image"
        assert context.target_model_id == "nano-banana-pro"
        assert context.status == "active"
        assert context.expires_at is not None
        assert context.expires_at > datetime.now(UTC)

        restored = await get_action_context(session, context.id, user.id)
        assert restored.id == context.id
        assert restored.opened_count == 1
        await session.commit()


@pytest.mark.asyncio
async def test_one_active_context_per_generation_action_is_reused() -> None:
    async with SessionFactory() as session:
        user = await _user(session)
        generation = _image_generation(user.id)
        session.add(generation)
        await session.commit()

        first = await create_action_context(
            session, user_id=user.id, generation=generation, action="remix"
        )
        second = await create_action_context(
            session, user_id=user.id, generation=generation, action="remix"
        )
        await session.commit()
        assert first.id == second.id


@pytest.mark.asyncio
async def test_action_context_is_owner_scoped() -> None:
    async with SessionFactory() as session:
        owner = await _user(session, "Owner")
        stranger = await _user(session, "Stranger")
        generation = _image_generation(owner.id)
        session.add(generation)
        await session.commit()

        context = await _resolved_context(session, owner, generation)

        with pytest.raises(ActionContextNotFoundError):
            await get_action_context(session, context.id, stranger.id)


@pytest.mark.asyncio
async def test_expired_action_context_is_rejected() -> None:
    async with SessionFactory() as session:
        user = await _user(session)
        generation = _image_generation(user.id)
        session.add(generation)
        await session.commit()

        context = await _resolved_context(session, user, generation)
        context.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

        with pytest.raises(ActionContextExpiredError):
            await get_action_context(session, context.id, user.id)


@pytest.mark.asyncio
async def test_mark_executed_is_idempotent() -> None:
    async with SessionFactory() as session:
        user = await _user(session)
        generation = _image_generation(user.id)
        session.add(generation)
        await session.commit()

        context = await create_action_context(
            session, user_id=user.id, generation=generation, action="animate"
        )
        await session.commit()

        assert await mark_action_context_executed(session, context.id, user.id) is True
        await session.commit()
        assert await mark_action_context_executed(session, context.id, user.id) is False
        assert context.status == "executed"


@pytest.mark.asyncio
async def test_create_context_api_rejects_wrong_owner() -> None:
    from fastapi import HTTPException

    from app.api.v1.generation_action_contexts import CreateActionContextRequest

    async with SessionFactory() as session:
        owner = await _user(session, "Owner")
        stranger = await _user(session, "Stranger")
        generation = _image_generation(owner.id)
        session.add(generation)
        await session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await create_context(
                generation.id,
                CreateActionContextRequest(action="remix"),
                stranger,
                session,
            )
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_read_context_api_endpoint_returns_snapshot_payload() -> None:
    async with SessionFactory() as session:
        user = await _user(session)
        generation = _image_generation(user.id)
        session.add(generation)
        await session.commit()

        context = await _resolved_context(session, user, generation)
        view = await read_context(context.id, user, session)
        assert view["action_context_id"] == str(context.id)
        assert view["action"]["id"] == "remix"
        assert view["defaults"]["model_id"] == "nano-banana-pro"
        assert view["generation"]["id"] == str(generation.id)
        assert view["target_mode"] == "image_to_image"


@pytest.mark.asyncio
async def test_publish_share_payload_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "bot_username", "roxy_share_test_bot")
    async with SessionFactory() as session:
        user = await _user(session)
        generation = _image_generation(user.id)
        generation.publication_scope = "feed"
        generation.is_public_feed = True
        generation.is_profile_visible = True
        session.add(generation)
        await session.commit()

        share = FeedService.share_payload(generation, user.telegram_id)
        assert set(share) == {"link", "share_url", "share_text", "copy_link"}
        assert share["copy_link"] == share["link"]
        assert share["link"]
        assert "feed_" in share["link"]
        assert "app?startapp" not in share["link"]
        assert share["share_url"].startswith("https://t.me/share/url?url=")
        assert share["share_text"].endswith(share["link"])


def test_animate_context_uses_grok_i2v_model_defaults() -> None:
    generation = _image_generation(uuid.uuid4())

    payload = build_action_context_payload(generation, "animate")

    assert payload["defaults"]["model_id"] == "grok-video-i2v"
    assert payload["defaults"]["parameters"] == {
        "aspect_ratio": "16:9",
        "mode": "normal",
        "duration": 6,
        "resolution": "480p",
        "nsfw_checker": False,
    }
