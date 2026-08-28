import random
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.v1.generations import (
    get_generation,
    hide_generation_from_history,
    list_generations,
    recreate_generation_payload,
    restore_generation_to_history,
)
from app.db.models import Generation, User
from app.db.session import SessionFactory


ROOT = Path(__file__).resolve().parents[1]


def _telegram_id(prefix: int) -> int:
    return prefix * 1_000_000_000_000 + random.randint(1, 999_999_999)


@pytest.mark.asyncio
async def test_history_is_owned_paginated_and_exposes_result_urls() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(21), first_name="History")
        other = User(telegram_id=_telegram_id(22), first_name="Other")
        session.add_all([user, other])
        await session.flush()

        first = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="succeeded",
            prompt="first",
            result_url="https://example.invalid/first.png",
            cost_rox=Decimal("8"),
            provider="kie",
            parameters={
                "_model_id": "nano-banana",
                "_result_urls": [
                    "https://example.invalid/first.png",
                    "https://example.invalid/second.png",
                ],
                "aspect_ratio": "1:1",
                "output_format": "png",
                "_kie_model": "private/provider-slug",
                "unexpected_provider_field": "must-not-leak",
            },
        )
        second = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="failed",
            prompt="second",
            cost_rox=Decimal("8"),
            provider="kie",
            error="provider failed",
            parameters={"_model_id": "nano-banana"},
        )
        foreign = Generation(
            user_id=other.id,
            kind="text_to_image",
            status="succeeded",
            prompt="private",
            result_url="https://example.invalid/private.png",
            cost_rox=Decimal("8"),
            provider="kie",
            parameters={"_model_id": "nano-banana"},
        )
        session.add_all([first, second, foreign])
        await session.commit()

        page_one = await list_generations(
            user,
            session,
            limit=1,
            before=None,
            status_filter=None,
        )
        assert len(page_one["items"]) == 1
        assert page_one["has_more"] is True
        assert page_one["next_before"]
        assert page_one["items"][0]["prompt"] != "private"

        page_two = await list_generations(
            user,
            session,
            limit=10,
            before=page_one["next_before"],
            status_filter=None,
        )
        assert len(page_two["items"]) == 1
        prompts = {page_one["items"][0]["prompt"], page_two["items"][0]["prompt"]}
        assert prompts == {"first", "second"}

        detail = await get_generation(first.id, user, session)
        assert detail["status"] == "succeeded"
        assert detail["result_urls"] == [
            "https://example.invalid/first.png",
            "https://example.invalid/second.png",
        ]
        assert detail["cost_credits"] == "8.00"
        assert detail["model"]["id"] == "nano-banana"
        assert detail["settings"] == {"aspect_ratio": "1:1", "output_format": "png"}
        assert detail["hidden_from_history"] is False

        with pytest.raises(HTTPException) as exc_info:
            await get_generation(foreign.id, user, session)
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_history_status_filter_is_server_side() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(23), first_name="Filter")
        session.add(user)
        await session.flush()
        session.add_all(
            [
                Generation(
                    user_id=user.id,
                    kind="text_to_image",
                    status="succeeded",
                    prompt="ok",
                    cost_rox=Decimal("8"),
                    provider="kie",
                    parameters={"_model_id": "nano-banana"},
                ),
                Generation(
                    user_id=user.id,
                    kind="text_to_image",
                    status="failed",
                    prompt="bad",
                    cost_rox=Decimal("8"),
                    provider="kie",
                    parameters={"_model_id": "nano-banana"},
                ),
            ]
        )
        await session.commit()

        page = await list_generations(
            user,
            session,
            limit=20,
            before=None,
            status_filter="failed",
        )
        assert [item["prompt"] for item in page["items"]] == ["bad"]


@pytest.mark.asyncio
async def test_history_hide_is_soft_and_restore_is_reversible() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(25), first_name="Hide")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="succeeded",
            prompt="keep accounting row",
            cost_rox=Decimal("8"),
            provider="kie",
            parameters={"_model_id": "nano-banana"},
        )
        session.add(generation)
        await session.commit()

        hidden = await hide_generation_from_history(generation.id, user, session)
        assert hidden == {"hidden": True}
        assert await session.get(Generation, generation.id) is not None

        page = await list_generations(
            user,
            session,
            limit=20,
            before=None,
            status_filter=None,
        )
        assert generation.id not in {item["id"] for item in page["items"]}

        detail = await get_generation(generation.id, user, session)
        assert detail["hidden_from_history"] is True

        restored = await restore_generation_to_history(generation.id, user, session)
        assert restored == {"hidden": False}
        page = await list_generations(
            user,
            session,
            limit=20,
            before=None,
            status_filter=None,
        )
        assert str(generation.id) in {item["id"] for item in page["items"]}


@pytest.mark.asyncio
async def test_recreate_payload_strips_provider_private_and_unknown_fields() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(24), first_name="Recreate")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="succeeded",
            prompt="reuse me",
            input_url="https://example.invalid/input.png",
            result_url="https://example.invalid/result.png",
            cost_rox=Decimal("8"),
            provider="kie",
            external_id="task-secret",
            parameters={
                "_model_id": "nano-banana",
                "_kie_model": "provider/slug",
                "_billing_mode": "flat",
                "_unit_price_rox": "8",
                "_result_urls": ["https://example.invalid/result.png"],
                "aspect_ratio": "1:1",
                "output_format": "png",
                "unexpected_provider_field": "must-not-leak",
            },
        )
        session.add(generation)
        await session.commit()

        payload = await recreate_generation_payload(generation.id, user, session)
        assert payload["model_id"] == "nano-banana"
        assert payload["prompt"] == "reuse me"
        assert payload["parameters"]["aspect_ratio"] == "1:1"
        assert payload["parameters"]["output_format"] == "png"
        assert "unexpected_provider_field" not in payload["parameters"]
        assert all(not key.startswith("_") for key in payload["parameters"])


@pytest.mark.asyncio
async def test_recreate_payload_of_seedance_parent_demands_fresh_references() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(25), first_name="Seedance Reuse")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_video",
            status="succeeded",
            prompt="dance like in the reference",
            input_url="https://example.invalid/first.png",
            result_url="https://example.invalid/result.mp4",
            cost_rox=Decimal("60"),
            provider="kie",
            external_id="task-secret",
            parameters={
                "_model_id": "seedance-2.0",
                "_billing_mode": "per_second",
                "_unit_price_rox": "11",
                "reference_image_urls": ["https://example.invalid/stale-subject.png"],
                "first_frame_url": "https://example.invalid/stale-first.png",
                "resolution": "720p",
                "aspect_ratio": "adaptive",
            },
        )
        session.add(generation)
        await session.commit()

        payload = await recreate_generation_payload(generation.id, user, session)
        assert payload["model_id"] == "seedance-2.0"
        assert payload["references_required"] is True
        assert payload["input_url"] is None
        for name in (
            "reference_image_urls",
            "reference_video_urls",
            "reference_audio_urls",
            "first_frame_url",
            "last_frame_url",
            "input_urls",
        ):
            assert name not in payload["parameters"]
        assert payload["parameters"]["resolution"] == "720p"
        assert payload["parameters"]["aspect_ratio"] == "adaptive"


@pytest.mark.asyncio
async def test_recreate_payload_of_text_only_seedance_parent_has_no_reference_flag() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(26), first_name="Seedance Text")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_video",
            status="succeeded",
            prompt="neon city flythrough",
            result_url="https://example.invalid/result.mp4",
            cost_rox=Decimal("55"),
            provider="kie",
            external_id="task-secret",
            parameters={
                "_model_id": "seedance-2.5",
                "resolution": "720p",
                "aspect_ratio": "adaptive",
            },
        )
        session.add(generation)
        await session.commit()

        payload = await recreate_generation_payload(generation.id, user, session)
        assert payload["model_id"] == "seedance-2.5"
        assert "references_required" not in payload
        assert payload["parameters"]["resolution"] == "720p"


def test_react_mini_app_contains_live_result_history_flow() -> None:
    app = (ROOT / "frontend" / "mini-app" / "components" / "roxy-app.tsx").read_text(
        encoding="utf-8"
    )
    api = (ROOT / "frontend" / "mini-app" / "lib" / "api.ts").read_text(encoding="utf-8")
    types = (ROOT / "frontend" / "mini-app" / "lib" / "types.ts").read_text(
        encoding="utf-8"
    )

    for token in (
        "const loadHistory",
        "setHistory",
        "HistoryScreen",
        "historyHasMore",
        "historyBefore",
        "Preview",
        "ACTIVE_STATUSES",
    ):
        assert token in app, token
    assert 'generations: (params = "limit=24")' in api
    assert 'generation: (id: string)' in api
    assert "result_urls?: string[]" in types
