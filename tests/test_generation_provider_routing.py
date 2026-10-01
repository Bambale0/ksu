from __future__ import annotations

from types import SimpleNamespace

from app.services.generation_provider_routing import route_for_model
from app.services.generation_worker import GenerationWorkerService


def test_new_seedance_routes_neironych_primary() -> None:
    assert route_for_model("seedance-2.0") == ("neironych", "kie")
    assert route_for_model("seedance-2.5") == ("neironych", "kie")


def test_new_nano_pro_routes_neironych_primary() -> None:
    assert route_for_model("nano-banana-pro") == ("neironych", "nexus")


def test_unmanaged_models_are_untouched() -> None:
    assert route_for_model("nano-banana-2") is None
    assert route_for_model("seedance-2.0-fast") is None


def test_worker_respects_persisted_provider() -> None:
    generation = SimpleNamespace(
        provider="kie",
        external_id="legacy-kie-task",
        parameters={"_model_id": "seedance-2.5", "_provider_route": ["neironych", "kie"]},
    )
    assert GenerationWorkerService._provider_name(generation) == "kie"
