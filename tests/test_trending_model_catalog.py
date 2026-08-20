from __future__ import annotations

import pytest

from app.services.model_catalog import ModelCatalog, UnknownModelError
from app.services.trending_model_catalog import (
    ACTIVE_NEW_WORK_MODEL_IDS,
    CURRENT_UTILITY_MODEL_IDS,
    TRENDING_PUBLIC_MODEL_IDS,
    TRENDING_PUBLIC_MODEL_ORDER,
)


def test_public_catalog_is_exact_trending_product_set() -> None:
    public_ids = [str(item["id"]) for item in ModelCatalog.list()]
    assert public_ids == list(TRENDING_PUBLIC_MODEL_ORDER)
    assert set(public_ids) == set(TRENDING_PUBLIC_MODEL_IDS)
    assert len(public_ids) == len(set(public_ids))


def test_current_tanyapi_families_remain_available() -> None:
    expected = {
        # Photo
        "nano-banana-2-lite",
        "seedream-5-pro-t2i",
        "seedream-5-pro-i2i",
        "nano-banana-pro",
        "nano-banana-2",
        "seedream-4.5-edit",
        "gpt-image-2-t2i",
        "gpt-image-2-i2i",
        "wan-2.7-image-pro",
        "grok-image-i2i",
        # Video
        "kling-3.0",
        "kling-2.5-turbo-pro-t2v",
        "kling-2.5-turbo-pro-i2v",
        "grok-video-i2v",
        "grok-video-1.5",
        "seedance-2.0",
        "seedance-2.5",
        "gemini-omni-video",
        "veo-3.1",
        "kling-motion-2.6",
        "kling-motion-3.0",
        "kling-avatar-standard",
        "kling-avatar-pro",
    }
    assert TRENDING_PUBLIC_MODEL_IDS == expected
    for model_id in expected:
        assert ModelCatalog.get(model_id).id == model_id


def test_old_catalog_versions_are_not_offered_for_new_work() -> None:
    stale_ids = {
        "nano-banana",
        "nano-banana-edit",
        "seedream-3-t2i",
        "seedream-4-t2i",
        "seedream-4-edit",
        "seedream-4.5-t2i",
        "seedream-5-lite-t2i",
        "seedream-5-lite-i2i",
        "seedream-5-pro-layers",
        "gpt-image-1.5-t2i",
        "gpt-image-1.5-i2i",
        "wan-2.7-image",
        "wan-2.7-t2v",
        "wan-2.7-i2v",
        "wan-2.7-video-edit",
        "wan-2.7-r2v",
        "seedance-1.5-pro",
        "seedance-2.0-fast",
        "seedance-2.0-mini",
        "grok-image-t2i",
        "grok-video-t2v",
    }
    public_ids = {str(item["id"]) for item in ModelCatalog.list()}
    assert stale_ids.isdisjoint(public_ids)
    assert stale_ids.isdisjoint(ACTIVE_NEW_WORK_MODEL_IDS)

    # Legacy specs stay readable for existing history/recovery rows, but cannot be
    # quoted/created again through the normal generation preparation boundary.
    assert ModelCatalog.get("seedream-3-t2i").id == "seedream-3-t2i"
    with pytest.raises(UnknownModelError, match="Inactive generation model"):
        ModelCatalog.prepare(
            "seedream-3-t2i",
            {"prompt": "legacy request"},
        )


def test_result_followup_operations_are_callable_but_not_picker_cards() -> None:
    assert CURRENT_UTILITY_MODEL_IDS == {"grok-video-upscale", "grok-video-extend"}
    assert CURRENT_UTILITY_MODEL_IDS <= ACTIVE_NEW_WORK_MODEL_IDS
    assert CURRENT_UTILITY_MODEL_IDS.isdisjoint(TRENDING_PUBLIC_MODEL_IDS)
