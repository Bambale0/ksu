from __future__ import annotations

import random
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import AdminUserNote, Generation, User
from app.db.session import SessionFactory
from app.providers.kie import KieTask
from app.services.generation_provider import GenerationProviderService


def _generation(
    *,
    user_id: uuid.UUID,
    provider: str,
    external_id: str,
    publication_scope: str = "private",
    is_public_feed: bool = False,
    is_profile_visible: bool = False,
) -> Generation:
    return Generation(
        user_id=user_id,
        kind="text_to_image",
        status="generating",
        prompt="entity integrity",
        cost_rox=Decimal("0"),
        provider=provider,
        external_id=external_id,
        parameters={"_model_id": "nano-banana"},
        publication_scope=publication_scope,
        is_public_feed=is_public_feed,
        is_profile_visible=is_profile_visible,
    )


async def _user(session) -> User:  # type: ignore[no-untyped-def]
    user = User(
        telegram_id=random.randint(20_000_000_000_000, 29_999_999_999_999),
        first_name="Integrity",
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_provider_task_identity_is_unique_within_provider() -> None:
    task_id = f"task-{uuid.uuid4()}"
    async with SessionFactory() as session:
        user = await _user(session)
        session.add(_generation(user_id=user.id, provider="kie", external_id=task_id))
        await session.commit()

        session.add(_generation(user_id=user.id, provider="kie", external_id=task_id))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_provider_task_identity_can_overlap_across_providers() -> None:
    task_id = f"task-{uuid.uuid4()}"
    async with SessionFactory() as session:
        user = await _user(session)
        session.add_all(
            [
                _generation(user_id=user.id, provider="kie", external_id=task_id),
                _generation(user_id=user.id, provider="other", external_id=task_id),
            ]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_kie_callback_selects_kie_generation_when_external_ids_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = f"task-{uuid.uuid4()}"

    class FakeKieClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def get_task(self, received_task_id: str) -> KieTask:
            return KieTask(
                task_id=received_task_id,
                state="processing",
                result_urls=[],
            )

    monkeypatch.setattr("app.services.generation_provider.KieClient", FakeKieClient)

    async with SessionFactory() as session:
        user = await _user(session)
        other = _generation(user_id=user.id, provider="other", external_id=task_id)
        kie = _generation(user_id=user.id, provider="kie", external_id=task_id)
        session.add_all([other, kie])
        await session.commit()

        result = await GenerationProviderService.sync_kie_task(
            session,
            task_id=task_id,
        )
        assert result is not None
        assert result.id == kie.id

        await session.refresh(other)
        assert other.status == "generating"
        assert other.error is None


@pytest.mark.asyncio
async def test_database_rejects_inconsistent_publication_state() -> None:
    async with SessionFactory() as session:
        user = await _user(session)
        session.add(
            _generation(
                user_id=user.id,
                provider="kie",
                external_id=f"task-{uuid.uuid4()}",
                publication_scope="feed",
                is_public_feed=False,
                is_profile_visible=True,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_admin_user_note_allows_null_admin_for_set_null_history() -> None:
    assert AdminUserNote.__table__.c.admin_id.nullable is True

    async with SessionFactory() as session:
        user = await _user(session)
        session.add(
            AdminUserNote(
                user_id=user.id,
                admin_id=None,
                body="historical note whose admin account was removed",
            )
        )
        await session.commit()
