from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.v1.generations import CreateGenerationRequest
from app.services.kie_video_contracts import KieVideoContractError, normalize_kie_video_input
from app.services.model_catalog import ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema
from app.services.seedance25_contract import normalize_seedance25_input
from app.services.seedance_prompt_limits import prompt_max_chars, validate_prompt_length


def _prompt_field(model_id: str) -> dict:
    model = ModelCatalog.get(model_id).public_dict()
    schema = build_public_model_ui_schema(model)
    return next(field for field in schema["fields"] if field["name"] == "prompt")


def test_seedance_prompt_limits_match_kie_contract() -> None:
    assert prompt_max_chars("seedance-2.0") == 20_000
    assert prompt_max_chars("seedance-2.0-fast") == 20_000
    assert prompt_max_chars("seedance-2.0-mini") == 20_000
    assert prompt_max_chars("seedance-2.5") == 30_000
    assert prompt_max_chars("nano-banana-2") == 8_000

    p20 = "a" * 20_000
    p25 = "b" * 30_000
    assert validate_prompt_length("seedance-2.0", p20) == p20
    assert validate_prompt_length("seedance-2.5", p25) == p25
    with pytest.raises(ValueError):
        validate_prompt_length("seedance-2.0", p20 + "x")
    with pytest.raises(ValueError):
        validate_prompt_length("seedance-2.5", p25 + "x")


def test_request_envelope_allows_seedance25_maximum() -> None:
    assert len(CreateGenerationRequest(model_id="seedance-2.5", prompt="x" * 30_000).prompt) == 30_000
    with pytest.raises(ValidationError):
        CreateGenerationRequest(model_id="seedance-2.5", prompt="x" * 30_001)


def test_provider_boundaries_reject_over_limit_without_truncating() -> None:
    p25 = "x" * 30_000
    assert normalize_seedance25_input({"prompt": p25})["prompt"] == p25
    with pytest.raises(Exception):
        normalize_seedance25_input({"prompt": p25 + "x"})

    p20 = "y" * 20_000
    normalized = normalize_kie_video_input("bytedance/seedance-2", {"prompt": p20})
    assert normalized["prompt"] == p20
    with pytest.raises(KieVideoContractError):
        normalize_kie_video_input("bytedance/seedance-2", {"prompt": p20 + "x"})


def test_miniapp_schema_exposes_exact_seedance_limits() -> None:
    assert _prompt_field("seedance-2.0")["max_length"] == 20_000
    assert _prompt_field("seedance-2.5")["max_length"] == 30_000
    for rel in ("roxy-app.tsx", "roxy-social-app.tsx"):
        source = Path("frontend/mini-app/components") / rel
        assert 'maxLength={field.max_length}' in source.read_text(encoding="utf-8")
