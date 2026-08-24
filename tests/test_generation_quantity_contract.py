import pytest
from pydantic import ValidationError

from app.api.v1.generations import CreateGenerationRequest, MAX_REQUEST_QUANTITY


def test_generation_quantity_defaults_to_one() -> None:
    payload = CreateGenerationRequest(model_id="seedance-2.0")

    assert payload.quantity == 1


def test_generation_quantity_allows_six() -> None:
    payload = CreateGenerationRequest(model_id="seedance-2.0", quantity=6)

    assert payload.quantity == 6
    assert MAX_REQUEST_QUANTITY == 6


def test_generation_quantity_rejects_more_than_six() -> None:
    with pytest.raises(ValidationError):
        CreateGenerationRequest(model_id="seedance-2.0", quantity=7)
