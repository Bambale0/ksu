from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.v1.generations import CreateGenerationRequest, MAX_REQUEST_QUANTITY


ROOT = Path(__file__).resolve().parents[1]
QUANTITY_CONTROL = ROOT / "frontend" / "mini-app" / "components" / "generation-quantity-control.tsx"


def test_generation_quantity_defaults_to_one() -> None:
    payload = CreateGenerationRequest(model_id="seedance-2.0")

    assert payload.quantity == 1


def test_generation_quantity_allows_four() -> None:
    payload = CreateGenerationRequest(model_id="seedance-2.0", quantity=4)

    assert payload.quantity == 4
    assert MAX_REQUEST_QUANTITY == 4


def test_generation_quantity_rejects_more_than_four() -> None:
    with pytest.raises(ValidationError):
        CreateGenerationRequest(model_id="seedance-2.0", quantity=5)


def test_mini_app_generation_quantity_fallback_is_four() -> None:
    source = QUANTITY_CONTROL.read_text(encoding="utf-8")

    assert "const DEFAULT_MAX_GENERATION_QUANTITY = 4;" in source
    assert "Math.min(DEFAULT_MAX_GENERATION_QUANTITY" in source
