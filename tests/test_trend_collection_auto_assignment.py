from __future__ import annotations

import uuid
from typing import Any

from app.db.admin_models import AdminRuntimeSetting, AdminTrend
from app.services.trend_collections import TrendCollectionService


class _Session:
    def __init__(self) -> None:
        self.setting = AdminRuntimeSetting(
            key=TrendCollectionService.SETTING_KEY,
            value=TrendCollectionService.merge_state(None),
        )
        self.trend = object()

    async def get(self, model: Any, key: Any) -> Any:
        if model is AdminRuntimeSetting:
            return self.setting
        if model is AdminTrend:
            return self.trend
        return None

    async def scalar(self, _statement: Any) -> Any:
        return self.setting

    def add(self, _value: Any) -> None:
        return None

    async def flush(self) -> None:
        return None


def test_birthday_collection_accepts_creator_friendly_aliases() -> None:
    state = TrendCollectionService.merge_state(None)

    assert TrendCollectionService.matching_collection(state, ["#др"]) == "birthday"
    assert TrendCollectionService.matching_collection(state, ["birthday"]) == "birthday"
    assert TrendCollectionService.matching_collection(state, ["#день-рождения"]) == "birthday"


async def test_auto_assignment_returns_to_default_when_tag_is_removed() -> None:
    session = _Session()
    trend_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    assigned = await TrendCollectionService.assign_from_tags(
        session,  # type: ignore[arg-type]
        admin_id=admin_id,
        trend_id=trend_id,
        tags=["#др"],
    )

    assert assigned == "birthday"
    state = TrendCollectionService.merge_state(session.setting.value)
    assert TrendCollectionService.assigned_collection(state, trend_id) == "birthday"
    assert str(trend_id) in state["auto_assignments"]

    assigned = await TrendCollectionService.assign_from_tags(
        session,  # type: ignore[arg-type]
        admin_id=admin_id,
        trend_id=trend_id,
        tags=[],
    )

    assert assigned is None
    state = TrendCollectionService.merge_state(session.setting.value)
    assert TrendCollectionService.assigned_collection(state, trend_id) == "trends"
    assert str(trend_id) not in state["auto_assignments"]


async def test_manual_folder_assignment_is_not_removed_by_missing_tags() -> None:
    session = _Session()
    trend_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    await TrendCollectionService.assign_trend(
        session,  # type: ignore[arg-type]
        admin_id=admin_id,
        trend_id=trend_id,
        collection_id="birthday",
    )
    await TrendCollectionService.assign_from_tags(
        session,  # type: ignore[arg-type]
        admin_id=admin_id,
        trend_id=trend_id,
        tags=[],
    )

    state = TrendCollectionService.merge_state(session.setting.value)
    assert TrendCollectionService.assigned_collection(state, trend_id) == "birthday"
    assert str(trend_id) not in state["auto_assignments"]


async def test_matching_tag_does_not_convert_manual_assignment_to_automatic() -> None:
    session = _Session()
    trend_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    await TrendCollectionService.assign_trend(
        session,  # type: ignore[arg-type]
        admin_id=admin_id,
        trend_id=trend_id,
        collection_id="birthday",
    )
    assigned = await TrendCollectionService.assign_from_tags(
        session,  # type: ignore[arg-type]
        admin_id=admin_id,
        trend_id=trend_id,
        tags=["#др"],
    )

    assert assigned == "birthday"
    state = TrendCollectionService.merge_state(session.setting.value)
    assert state["assignments"][str(trend_id)] == "birthday"
    assert str(trend_id) not in state["auto_assignments"]
