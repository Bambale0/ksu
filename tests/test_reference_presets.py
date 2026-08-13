from __future__ import annotations

import random
import uuid

import pytest

from app.db.models import User
from app.db.session import SessionFactory
from app.services.references import ReferenceService
from app.services.user_presets import PresetError, UserPresetService


async def _user(session) -> User:  # type: ignore[no-untyped-def]
    row = User(
        telegram_id=random.randint(9_300_000_000_000, 9_399_999_999_999),
        first_name="Reference test",
    )
    session.add(row)
    await session.commit()
    return row


@pytest.mark.asyncio
async def test_reference_registration_is_idempotent_and_owner_scoped() -> None:
    async with SessionFactory() as session:
        owner = await _user(session)
        other = await _user(session)
        url = f"https://cdn.example.invalid/{uuid.uuid4()}.png"
        first, replayed_first = await ReferenceService.register(
            session, user_id=owner.id, source_url=url, kind="image", label="Hero"
        )
        second, replayed_second = await ReferenceService.register(
            session, user_id=owner.id, source_url=url, kind="image", label="Hero updated"
        )
        assert replayed_first is False
        assert replayed_second is True
        assert first.id == second.id
        assert second.label == "Hero updated"
        with pytest.raises(LookupError):
            await ReferenceService.get_owned(session, user_id=other.id, reference_id=first.id)


@pytest.mark.asyncio
async def test_reference_soft_delete_hides_item() -> None:
    async with SessionFactory() as session:
        owner = await _user(session)
        row, _ = await ReferenceService.register(
            session,
            user_id=owner.id,
            source_url=f"https://cdn.example.invalid/{uuid.uuid4()}.jpg",
            kind="image",
        )
        reference_id = row.id
        await ReferenceService.remove(session, user_id=owner.id, reference_id=reference_id)
        rows = await ReferenceService.list_owned(session, user_id=owner.id)
        assert all(item.id != reference_id for item in rows)


@pytest.mark.asyncio
async def test_preset_validates_model_fields_and_reference_ownership() -> None:
    async with SessionFactory() as session:
        owner = await _user(session)
        other = await _user(session)
        ref, _ = await ReferenceService.register(
            session,
            user_id=owner.id,
            source_url=f"https://cdn.example.invalid/{uuid.uuid4()}.png",
            kind="image",
        )
        reference_id = ref.id
        preset = await UserPresetService.create(
            session,
            user_id=owner.id,
            name="Portrait",
            model_id="nano-banana-pro",
            prompt="cinematic portrait",
            parameters={"aspect_ratio": "1:1", "resolution": "2K"},
            reference_ids=[reference_id],
        )
        assert preset.reference_ids == [str(reference_id)]
        with pytest.raises(PresetError):
            await UserPresetService.create(
                session,
                user_id=owner.id,
                name="Invalid field",
                model_id="nano-banana-pro",
                prompt="portrait",
                parameters={"not_a_model_field": True},
                reference_ids=[],
            )
        with pytest.raises(LookupError):
            await UserPresetService.create(
                session,
                user_id=other.id,
                name="Foreign reference",
                model_id="nano-banana-pro",
                prompt="portrait",
                parameters={},
                reference_ids=[reference_id],
            )
