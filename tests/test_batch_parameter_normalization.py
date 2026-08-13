from __future__ import annotations

import pytest

from app.services.batch_generation_core import BatchGenerationError, normalize_parameters


def test_batch_json_parameters_are_normalized() -> None:
    payload = normalize_parameters(
        {
            "bbox_list": '[{"x": 1, "y": 2}]',
            "audio_setting": '{"enabled": true}',
            "aspect_ratio": "1:1",
        }
    )
    assert payload["bbox_list"] == [{"x": 1, "y": 2}]
    assert payload["audio_setting"] == {"enabled": True}
    assert payload["aspect_ratio"] == "1:1"


def test_batch_invalid_json_parameter_is_rejected() -> None:
    with pytest.raises(BatchGenerationError):
        normalize_parameters({"bbox_list": "{broken"})
