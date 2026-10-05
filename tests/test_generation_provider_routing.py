from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.generation_provider_routing import configured_routes, route_for_model, route_options
from app.services.generation_worker import GenerationWorkerService


def test_supported_models_use_expected_primary_routes() -> None:
    assert route_for_model("seedance-2.0") == ("neironych", "nexus", "kie")
    assert route_for_model("seedance-2.5") == ("neironych", "nexus", "kie")
    assert route_for_model("nano-banana-pro") == ("nexus", "neironych", "kie")
    assert route_for_model("nano-banana-2") == ("nexus", "kie")
    assert route_for_model("seedance-2.0-fast") == ("nexus", "kie")
    assert route_for_model("veo-3.1") == ("nexus", "kie")


def test_grok_and_nexus_incompatible_models_are_untouched() -> None:
    assert route_for_model("grok-video-t2v") is None
    assert route_for_model("grok-image-t2i") is None
    assert route_for_model("seedream-5-pro-layers") is None
    assert route_for_model("kling-motion-3.0") is None


def test_worker_respects_persisted_provider() -> None:
    generation = SimpleNamespace(
        provider="kie",
        external_id="legacy-kie-task",
        parameters={
            "_model_id": "seedance-2.5",
            "_provider_route": ["nexus", "neironych", "kie"],
        },
    )
    assert GenerationWorkerService._provider_name(generation) == "kie"


@pytest.mark.asyncio
async def test_legacy_runtime_route_row_bootstraps_current_registry() -> None:
    class Row:
        value = {
            "revision": 7,
            "routes": {
                "seedance-2.0": ["neironych", "kie"],
                "seedance-2.5": ["neironych", "kie"],
                "nano-banana-pro": ["neironych", "nexus"],
            },
        }

    class StubSession:
        async def get(self, *_args, **_kwargs):
            return Row()

    config = await configured_routes(StubSession())  # type: ignore[arg-type]

    assert config["revision"] == 7
    assert config["routes"]["seedance-2.0"][0] == "neironych"
    assert config["routes"]["nano-banana-pro"][0] == "nexus"
    assert config["routes"]["veo-3.1"] == ["nexus", "kie"]
    assert all(not model.startswith("grok-") for model in config["routes"])


@pytest.mark.asyncio
async def test_full_runtime_row_migrates_only_superseded_seedance_defaults() -> None:
    routes = {model: choices[0] for model, choices in route_options().items()}
    routes["seedance-2.0"] = ["nexus", "neironych", "kie"]
    routes["seedance-2.5"] = ["nexus", "neironych", "kie"]
    routes["nano-banana-pro"] = ["nexus"]

    class Row:
        value = {"revision": 11, "routes": routes}

    class StubSession:
        async def get(self, *_args, **_kwargs):
            return Row()

    config = await configured_routes(StubSession())  # type: ignore[arg-type]

    assert config["revision"] == 11
    assert config["routes"]["seedance-2.0"] == ["neironych", "nexus", "kie"]
    assert config["routes"]["seedance-2.5"] == ["neironych", "nexus", "kie"]
    assert config["routes"]["nano-banana-pro"] == ["nexus"]
