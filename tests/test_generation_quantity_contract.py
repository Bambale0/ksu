import pytest
from pydantic import ValidationError

from app.api.v1.generations import CreateGenerationRequest, MAX_REQUEST_QUANTITY


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
