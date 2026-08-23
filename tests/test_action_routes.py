"""API contract and end-to-end scenario tests for generation action contexts."""

from __future__ import annotations

import random
import uuid
from decimal import Decimal

import pytest

from app.api.v1.generation_action_contexts import (
    CreateActionContextRequest,
    create_context,
    read_context,
    read_context_alias,
)
from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.services.generation_action_contexts import (
    ActionContextNotFoundError,
    get_action_context,
    mark_action_context_executed,
)


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


async def _user(session, name: str = "Routes") -> User:  # type: ignore[no-untyped-def]
    user = User(telegram_id=_telegram_id(), first_name=name)
    session.add(user)
    await session.flush()
    return user


# --- API contract ------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_context_contract_returns_route_and_expiry() -> None:
    async with SessionFactory() as session:
        user = await _user(session)
        generation = _image_generation(user.id)
        session.add(generation)
        await session.commit()

        view = await create_context(
            generation.id,
            CreateActionContextRequest(action="edit"),
            user,
            session,
        )

        assert view["action_context_id"] == view["id"]
        assert view["action"] == "edit"
        assert "action_context_id=" in str(view["route"])
        assert "route=generation-action" in str(view["route"])
        assert view["target_mode"] == "image_to_image"
        assert view["status"] == "active"
        assert view["expires_at"]


@pytest.mark.asyncio
async def test_alias_read_route_matches_canonical_route() -> None:
    async with SessionFactory() as session:
        user = await _user(session)
        generation = _image_generation(user.id)
        session.add(generation)
        await session.commit()

        created = await create_context(
            generation.id,
            CreateActionContextRequest(action="animate"),
            user,
            session,
        )
        context_id = uuid.UUID(str(created["id"]))

        canonical = await read_context(context_id, user, session)
        alias = await read_context_alias(context_id, user, session)
        assert canonical == alias
        assert canonical["action"]["id"] == "animate"


@pytest.mark.asyncio
async def test_execute_marks_context_consumed_once() -> None:
    async with SessionFactory() as session:
        user = await _user(session)
        generation = _image_generation(user.id)
        session.add(generation)
        await session.commit()

        created = await create_context(
            generation.id,
            CreateActionContextRequest(action="repeat"),
            user,
            session,
        )

        context_id = uuid.UUID(str(created["id"]))
        assert await mark_action_context_executed(session, context_id, user.id) is True
        await session.commit()
        assert await mark_action_context_executed(session, context_id, user.id) is False


# --- Permissions -------------------------------------------------------------


@pytest.mark.asyncio
async def test_foreign_user_cannot_read_or_consume_context() -> None:
    async with SessionFactory() as session:
        owner = await _user(session, "Owner")
        stranger = await _user(session, "Stranger")
        generation = _image_generation(owner.id)
        session.add(generation)
        await session.commit()

        created = await create_context(
            generation.id,
            CreateActionContextRequest(action="remix"),
            owner,
            session,
        )
        context_id = uuid.UUID(str(created["id"]))

        with pytest.raises(ActionContextNotFoundError):
            await get_action_context(session, context_id, stranger.id)

        assert await mark_action_context_executed(session, context_id, stranger.id) is False


# --- E2E scenarios -----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_mode"),
    [("remix", None), ("edit", "image_to_image"), ("animate", "image_to_video")],
)
async def test_image_result_scenarios_restore_prefilled_flow(
    action: str, expected_mode: str | None
) -> None:
    """Generate image -> click action -> prefilled screen with restored context."""
    async with SessionFactory() as session:
        user = await _user(session)
        generation = _image_generation(user.id)
        session.add(generation)
        await session.commit()

        created = await create_context(
            generation.id,
            CreateActionContextRequest(action=action),
            user,
            session,
        )
        context = await get_action_context(session, uuid.UUID(str(created["id"])), user.id)
        await session.commit()

        payload = dict(context.payload_json)
        assert payload["action"]["id"] == action
        assert payload["source_url"] == generation.result_url
        scenario = payload.get("scenario") or {}
        if expected_mode is not None:
            assert scenario["mode"] == expected_mode
        else:
            # Remix restores the original intent instead of forcing a mode.
            assert scenario["prompt"]
        assert scenario["model"]
        # The Mini App can restore the exact screen from the short id alone.
        restored = await get_action_context(session, context.id, user.id)
        assert restored.payload_json == context.payload_json
