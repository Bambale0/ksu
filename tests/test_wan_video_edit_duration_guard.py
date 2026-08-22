from __future__ import annotations

import pytest

from app.services.kie_video_contracts import KieVideoContractError, normalize_kie_video_input
from app.services.model_catalog import InvalidModelParametersError, ModelCatalog


@pytest.mark.parametrize("duration", [0, *range(2, 11)])
def test_wan_video_edit_accepts_current_callable_durations(duration: int) -> None:
    spec, clean, _cost, _seconds, _unit = ModelCatalog.prepare(
        "wan-2.7-video-edit",
        {
            "prompt": "edit",
            "video_url": "https://example.com/source.mp4",
            "duration": duration,
        },
        billing_seconds=6 if duration == 0 else None,
    )
    assert spec.id == "wan-2.7-video-edit"
    assert clean["duration"] == duration

    payload = normalize_kie_video_input(
        spec.kie_model,
        {
            "prompt": "edit",
            "video_url": "https://example.com/source.mp4",
            "duration": duration,
        },
    )
    assert payload["duration"] == duration


@pytest.mark.parametrize("duration", [1, 11, 30, 60])
def test_wan_video_edit_rejects_retired_direct_api_durations(duration: int) -> None:
    with pytest.raises(InvalidModelParametersError, match="Auto.*2-10"):
        ModelCatalog.prepare(
            "wan-2.7-video-edit",
            {
                "prompt": "edit",
                "video_url": "https://example.com/source.mp4",
                "duration": duration,
            },
        )

    with pytest.raises(KieVideoContractError, match="Auto.*2-10"):
        normalize_kie_video_input(
            "wan/2-7-videoedit",
            {
                "prompt": "edit",
                "video_url": "https://example.com/source.mp4",
                "duration": duration,
            },
        )
