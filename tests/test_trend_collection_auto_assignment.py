from __future__ import annotations

import random
import uuid

import pytest

from app.db.admin_models import AdminTrend, TrendCollectionAssignment
from app.db.models import AdminAccount, User
from app.db.session import SessionFactory
from app.services.trend_collections import TrendCollectionService


def _telegram_id() -> int:
    return 98_700_000_000_000 + random.randint(1, 999_999_999)


async def _admin_and_trend(session, *, tags: list[str]) -> tuple[AdminAccount, AdminTrend]:  # type: ignore[no-untyped-def]
    user = User(telegram_id=_telegram_id(), first_name="TrendCollection")
    session.add(user)
    await session.flush()
    admin = AdminAccount(user_id=user.id, role="superadmin")
    session.add(admin)
    await session.flush()
    trend = AdminTrend(
        title="Collection assignment test",
        payload={"tags": tags},
        is_active=True,
        created_by_admin_id=admin.id,
    )
    session.add(trend)
    await session.flush()
    return admin, trend


async def _category(session, *, admin_id: uuid.UUID, tag: str) -> str:  # type: ignore[no-untyped-def]
    category_id = f"folder-{uuid.uuid4().hex[:12]}"
    await TrendCollectionService.upsert_collection(
        session,
        admin_id=admin_id,
        collection_id=category_id,
        payload={
            "title": f"Категория {category_id[-6:]}",
            "description": "",
            "aliases": [tag],
            "sort_order": 100,
            "is_active": True,
        },
    )
    return category_id


def test_birthday_collection_accepts_creator_friendly_aliases() -> None:
    state = TrendCollectionService.merge_state(None)

    assert TrendCollectionService.matching_collection(state, ["#др"]) == "birthday"
    assert TrendCollectionService.matching_collection(state, ["birthday"]) == "birthday"
    assert TrendCollectionService.matching_collection(state, ["#день-рождения"]) == "birthday"


@pytest.mark.asyncio
async def test_auto_assignment_returns_to_default_when_tag_is_removed() -> None:
    tag = f"auto-{uuid.uuid4().hex[:10]}"
    async with SessionFactory() as session:
        admin, trend = await _admin_and_trend(session, tags=[tag])
        category_id = await _category(session, admin_id=admin.id, tag=tag)

        assigned = await TrendCollectionService.assign_from_tags(
            session,
            admin_id=admin.id,
            trend_id=trend.id,
            tags=[tag],
        )
        assert assigned == category_id

        state = await TrendCollectionService.state(session)
        assert TrendCollectionService.assigned_collection(state, trend.id) == category_id
        row = await session.get(TrendCollectionAssignment, trend.id)
        assert row is not None and row.automatic is True

        assigned = await TrendCollectionService.assign_from_tags(
            session,
            admin_id=admin.id,
            trend_id=trend.id,
            tags=[],
        )
        assert assigned is None

        state = await TrendCollectionService.state(session)
        assert TrendCollectionService.assigned_collection(state, trend.id) == "trends"
        assert await session.get(TrendCollectionAssignment, trend.id) is None


@pytest.mark.asyncio
async def test_manual_category_assignment_is_not_removed_by_missing_tags() -> None:
    tag = f"manual-{uuid.uuid4().hex[:10]}"
    async with SessionFactory() as session:
        admin, trend = await _admin_and_trend(session, tags=[])
        category_id = await _category(session, admin_id=admin.id, tag=tag)

        await TrendCollectionService.assign_trend(
            session,
            admin_id=admin.id,
            trend_id=trend.id,
            collection_id=category_id,
        )
        await TrendCollectionService.assign_from_tags(
            session,
            admin_id=admin.id,
            trend_id=trend.id,
            tags=[],
        )

        state = await TrendCollectionService.state(session)
        assert TrendCollectionService.assigned_collection(state, trend.id) == category_id
        row = await session.get(TrendCollectionAssignment, trend.id)
        assert row is not None and row.automatic is False


@pytest.mark.asyncio
async def test_matching_tag_does_not_convert_manual_assignment_to_automatic() -> None:
    tag = f"pinned-{uuid.uuid4().hex[:10]}"
    async with SessionFactory() as session:
        admin, trend = await _admin_and_trend(session, tags=[tag])
        category_id = await _category(session, admin_id=admin.id, tag=tag)

        await TrendCollectionService.assign_trend(
            session,
            admin_id=admin.id,
            trend_id=trend.id,
            collection_id=category_id,
        )
        assigned = await TrendCollectionService.assign_from_tags(
            session,
            admin_id=admin.id,
            trend_id=trend.id,
            tags=[tag],
        )

        assert assigned == category_id
        row = await session.get(TrendCollectionAssignment, trend.id)
        assert row is not None
        assert row.collection_id == category_id
        assert row.automatic is False


@pytest.mark.asyncio
async def test_manual_move_to_live_trends_remains_authoritative() -> None:
    tag = f"root-pin-{uuid.uuid4().hex[:10]}"
    async with SessionFactory() as session:
        admin, trend = await _admin_and_trend(session, tags=[tag])
        category_id = await _category(session, admin_id=admin.id, tag=tag)

        await TrendCollectionService.assign_trend(
            session,
            admin_id=admin.id,
            trend_id=trend.id,
            collection_id="trends",
        )
        assigned = await TrendCollectionService.assign_from_tags(
            session,
            admin_id=admin.id,
            trend_id=trend.id,
            tags=[tag],
        )

        assert assigned == "trends"
        row = await session.get(TrendCollectionAssignment, trend.id)
        assert row is not None
        assert row.collection_id == "trends"
        assert row.automatic is False

        # The category exists and would otherwise match, proving the manual root
        # assignment—not lack of a match—blocked automatic movement.
        state = await TrendCollectionService.state(session)
        assert TrendCollectionService.matching_collection(state, [tag]) == category_id
