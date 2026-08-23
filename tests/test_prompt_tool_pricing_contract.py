from __future__ import annotations

from decimal import Decimal

from app.services import prompt_tools


def test_default_prompt_tools_are_not_free() -> None:
    assert prompt_tools._DEFAULT_COSTS["prompt_builder"] == Decimal("10.00")
    assert prompt_tools._DEFAULT_COSTS["image_analysis"] == Decimal("15.00")
    assert prompt_tools._DEFAULT_COSTS["video_prompt"] == Decimal("30.00")
    assert all(amount > 0 for amount in prompt_tools._DEFAULT_COSTS.values())
