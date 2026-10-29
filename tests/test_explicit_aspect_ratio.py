from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.generation_action_contexts import _context_meta
from app.api.v1.generation_actions import DeriveGenerationRequest, derive_generation
from app.db.models import Generation
from app.services.billing_access import BillingAccessService
from app.services.generation_action_contexts import build_action_context_payload
from app.services.generation_reliability import GenerationOutboxService
from app.services.generations import GenerationService
from app.services.model_catalog import InvalidModelParametersError, ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema
from app.services.media_assets import MediaAssetService
from app.services.trend_workflows import TrendWorkflowError, TrendWorkflowService
from app.services.trends import TrendService
from app.services.wallet import WalletService


def _ratio_field(schema: dict) -> dict:
    return next(field for field in schema["fields"] if field["name"] == "aspect_ratio")


def test_public_model_schemas_never_offer_or_default_to_auto_aspect_ratio() -> None:
    for model in ModelCatalog.list():
        schema = build_public_model_ui_schema(model)
        ratio = next((field for field in schema["fields"] if field["name"] == "aspect_ratio"), None)
        if ratio:
            assert all(str(value).strip().casefold() != "auto" for value in ratio.get("suggestions", [])), model["id"]
        assert str(schema.get("defaults", {}).get("aspect_ratio", "")).strip().casefold() != "auto", model["id"]


@pytest.mark.parametrize("model_id", ["nano-banana-2", "nano-banana-2-lite", "gpt-image-2-t2i", "gpt-image-2-i2i", "grok-video-1.5"])
def test_former_auto_defaults_require_user_choice_without_a_replacement(model_id: str) -> None:
    schema = build_public_model_ui_schema(ModelCatalog.get(model_id).public_dict())
    assert _ratio_field(schema)["required"] is True
    assert "aspect_ratio" not in schema["defaults"]


@pytest.mark.parametrize("model_id,parameters", [
    ("nano-banana-2-lite", {}),
    ("nano-banana-2", {}),
    ("gpt-image-2-t2i", {}),
    ("grok-video-1.5", {"duration": 8}),
])
@pytest.mark.parametrize("ratio", [None, "", "auto", "AUTO", " Auto "])
async def test_new_admission_requires_explicit_ratio(model_id: str, parameters: dict, ratio: str | None) -> None:
    parameters = {**parameters, **({"aspect_ratio": ratio} if ratio is not None else {})}
    with pytest.raises(InvalidModelParametersError, match="[Aa]spect ratio|соотношение сторон"):
        await GenerationService.prepare_request(object(), model_id=model_id, prompt="A mountain", parameters=parameters)


@pytest.mark.parametrize("ratio", ["1:1", "16:9", "9:16", "4:3", "3:4"])
async def test_explicit_lite_ratio_is_preserved(ratio: str) -> None:
    _spec, clean, _cost, _seconds, _unit = await GenerationService.prepare_request(
        object(), model_id="nano-banana-2-lite", prompt="A mountain", parameters={"aspect_ratio": ratio}
    )
    assert clean["aspect_ratio"] == ratio


async def test_removed_auto_is_blocked_before_billing_or_outbox(monkeypatch: pytest.MonkeyPatch) -> None:
    billing = AsyncMock(side_effect=AssertionError("billing must not run"))
    debit = AsyncMock(side_effect=AssertionError("debit must not run"))
    outbox = Mock(side_effect=AssertionError("outbox must not run"))
    monkeypatch.setattr(BillingAccessService, "decision", billing)
    monkeypatch.setattr(WalletService, "debit", debit)
    monkeypatch.setattr(GenerationOutboxService, "add", outbox)
    with pytest.raises(InvalidModelParametersError, match="[Aa]spect ratio|соотношение сторон"):
        await GenerationService.create(
            object(), object(), user_id=uuid4(), model_id="nano-banana-2-lite",
            prompt="A mountain", parameters={"aspect_ratio": "auto"},
        )
    billing.assert_not_awaited()
    debit.assert_not_awaited()
    outbox.assert_not_called()


async def test_structural_preflight_retains_legacy_auto_without_admitting_a_job() -> None:
    _spec, clean, _cost, _seconds, _unit = await GenerationService.prepare_template_request(
        object(), model_id="nano-banana-2-lite", prompt="A mountain", parameters={"aspect_ratio": "auto"}
    )
    assert clean["aspect_ratio"] == "auto"


async def test_fixed_defaults_and_seedance_adaptive_keep_existing_semantics() -> None:
    _spec, clean, *_ = await GenerationService.prepare_request(
        object(), model_id="nano-banana-pro", prompt="A mountain", parameters={}
    )
    assert clean.get("aspect_ratio") in (None, "1:1")
    wan_schema = build_public_model_ui_schema(ModelCatalog.get("wan-2.7-video-edit").public_dict())
    assert wan_schema["defaults"]["audio_setting"] == "auto"
    assert wan_schema["defaults"]["duration"] == 5
    duration_field = next(field for field in wan_schema["fields"] if field["name"] == "duration")
    assert 0 in duration_field["suggestions"]


@pytest.mark.parametrize("model_id", ["seedance-2.0", "seedance-2.5"])
async def test_seedance_technical_adaptive_semantics_are_preserved(model_id: str) -> None:
    _spec, clean, *_ = await GenerationService.prepare_request(
        object(), model_id=model_id, prompt="A mountain", parameters={"aspect_ratio": "adaptive", "duration": 5}
    )
    assert clean["aspect_ratio"] == "adaptive"


async def test_kling_frame_ratio_stays_omitted_and_explicit_ratio_stays_invalid() -> None:
    parameters = {"duration": 5, "mode": "pro", "image_urls": ["https://cdn.example/image.jpg"]}
    _spec, clean, *_ = await GenerationService.prepare_request(
        object(), model_id="kling-3.0", prompt="Animate", parameters=parameters,
    )
    assert "aspect_ratio" not in clean
    with pytest.raises(InvalidModelParametersError, match="aspect_ratio must be omitted"):
        await GenerationService.prepare_request(
            object(), model_id="kling-3.0", prompt="Animate",
            parameters={**parameters, "aspect_ratio": "16:9"},
        )


async def test_seedance_frame_alias_keeps_current_multimodal_routing_and_fixed_ratio() -> None:
    _spec, clean, *_ = await GenerationService.prepare_request(
        object(), model_id="seedance-2.5", prompt="Animate @Image1",
        parameters={"duration": 5, "aspect_ratio": "9:16", "first_frame_url": "https://cdn.example/image.jpg"},
    )
    assert clean["aspect_ratio"] == "9:16"
    assert clean["reference_image_urls"] == ["https://cdn.example/image.jpg"]
    assert "first_frame_url" not in clean


def _legacy_generation() -> Generation:
    return Generation(
        id=uuid4(), user_id=uuid4(), kind="text_to_image", status="succeeded",
        prompt="A portrait", result_url="https://cdn.example/result.png",
        cost_rox=Decimal("20"), provider="kie",
        parameters={"_model_id": "nano-banana-pro", "_media_type": "image", "aspect_ratio": "auto"},
    )


def test_repeat_context_requires_choice_for_old_auto_without_mutating_history() -> None:
    generation = _legacy_generation()
    original = deepcopy(generation.parameters)
    payload = build_action_context_payload(generation, "repeat")
    assert "aspect_ratio" not in payload["defaults"]["parameters"]
    candidate = next(item for item in payload["candidate_models"] if item["id"] == "nano-banana-pro")
    assert _ratio_field(candidate["ui_schema"])["required"] is True
    assert "aspect_ratio" not in candidate["ui_schema"]["defaults"]
    if payload.get("scenario"):
        assert "aspect_ratio" not in payload["scenario"]["settings"]
    assert generation.parameters == original


@pytest.mark.parametrize("ratio", [None, "", "   ", "auto", " AUTO "])
async def test_repeat_api_cannot_clear_legacy_auto_into_a_fixed_default(
    monkeypatch: pytest.MonkeyPatch, ratio: str | None,
) -> None:
    parent = _legacy_generation()
    create = AsyncMock(return_value=SimpleNamespace(id=uuid4(), status="queued", cost_rox=Decimal("20"), action_type="repeat"))
    monkeypatch.setattr(GenerationService, "create", create)
    session = SimpleNamespace(get=AsyncMock(return_value=parent))
    with pytest.raises(HTTPException) as error:
        await derive_generation(
            parent.id, "repeat",
            DeriveGenerationRequest(model_id="nano-banana-pro", parameters={"aspect_ratio": ratio}),
            SimpleNamespace(id=parent.user_id), session, object(),
        )
    assert error.value.status_code == 422
    create.assert_not_awaited()
    assert parent.parameters["aspect_ratio"] == "auto"


async def test_repeat_api_preserves_explicit_override_for_legacy_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    parent = _legacy_generation()
    create = AsyncMock(return_value=SimpleNamespace(id=uuid4(), status="queued", cost_rox=Decimal("20"), action_type="repeat"))
    monkeypatch.setattr(GenerationService, "create", create)
    await derive_generation(
        parent.id, "repeat",
        DeriveGenerationRequest(model_id="nano-banana-pro", parameters={"aspect_ratio": "9:16"}),
        SimpleNamespace(id=parent.user_id), SimpleNamespace(get=AsyncMock(return_value=parent)), object(),
    )
    assert create.await_args.kwargs["parameters"]["aspect_ratio"] == "9:16"
    assert parent.parameters["aspect_ratio"] == "auto"


@pytest.mark.parametrize("overrides", [{}, {"aspect_ratio": None}, {"aspect_ratio": ""}])
async def test_repeat_api_preserves_kling_source_frame_omission(monkeypatch: pytest.MonkeyPatch, overrides: dict) -> None:
    parent = _legacy_generation()
    parent.parameters = {
        "_model_id": "kling-3.0", "_media_type": "video", "aspect_ratio": "auto",
        "image_urls": ["https://cdn.example/frame.jpg"], "duration": 5, "mode": "pro",
    }
    parent.kind = "image_to_video"
    parent.result_url = "https://cdn.example/result.mp4"
    create = AsyncMock(return_value=SimpleNamespace(id=uuid4(), status="queued", cost_rox=Decimal("20"), action_type="repeat"))
    monkeypatch.setattr(GenerationService, "create", create)
    await derive_generation(
        parent.id, "repeat",
        DeriveGenerationRequest(model_id="kling-3.0", parameters=overrides),
        SimpleNamespace(id=parent.user_id), SimpleNamespace(get=AsyncMock(return_value=parent)), object(),
    )
    assert create.await_args.kwargs["parameters"].get("aspect_ratio") is None
    assert create.await_args.kwargs["parameters"]["image_urls"] == ["https://cdn.example/frame.jpg"]


@pytest.mark.parametrize("stored", [False, True])
def test_kling_frame_context_omits_ratio_control_for_fresh_and_stored_reads(stored: bool) -> None:
    parent = _legacy_generation()
    parent.parameters = {
        "_model_id": "kling-3.0", "_media_type": "video", "aspect_ratio": "auto",
        "image_urls": ["https://cdn.example/frame.jpg"], "duration": 5, "mode": "pro",
    }
    parent.kind = "image_to_video"
    parent.result_url = "https://cdn.example/result.mp4"
    payload = build_action_context_payload(parent, "repeat")
    if stored:
        candidate = next(item for item in payload["candidate_models"] if item["id"] == "kling-3.0")
        candidate["ui_schema"] = build_public_model_ui_schema(ModelCatalog.get("kling-3.0").public_dict())
        _ratio_field(candidate["ui_schema"])["required"] = True
        _ratio_field(candidate["ui_schema"])["suggestions"] = ["auto", "16:9"]
        payload["defaults"]["parameters"]["aspect_ratio"] = "auto"
        stored_payload = payload
        original = deepcopy(payload)
        payload = _context_meta(SimpleNamespace(
            id=uuid4(), payload_json=payload, status="active", expires_at=None,
            target_mode="text_to_video", target_model_id="kling-3.0",
        ))
        assert stored_payload == original
    candidate = next(item for item in payload["candidate_models"] if item["id"] == "kling-3.0")
    assert all(field["name"] != "aspect_ratio" for field in candidate["ui_schema"]["fields"])
    assert "aspect_ratio" not in candidate["ui_schema"]["defaults"]
    assert "aspect_ratio" not in payload["defaults"]["parameters"]
    assert parent.parameters["aspect_ratio"] == "auto"


def test_stored_context_read_filters_stale_ratio_options_without_writing_snapshot() -> None:
    generation = _legacy_generation()
    payload = build_action_context_payload(generation, "repeat")
    payload["defaults"]["parameters"]["aspect_ratio"] = " Auto "
    candidate = next(item for item in payload["candidate_models"] if item["id"] == "nano-banana-pro")
    candidate["ui_schema"]["defaults"]["aspect_ratio"] = "auto"
    _ratio_field(candidate["ui_schema"])["suggestions"] = ["auto", "1:1", "16:9"]
    original = deepcopy(payload)
    context = SimpleNamespace(
        id=uuid4(), payload_json=payload, status="active", expires_at=None,
        target_mode="text_to_image", target_model_id="nano-banana-pro",
    )
    public = _context_meta(context)
    assert "aspect_ratio" not in public["defaults"]["parameters"]
    candidate = next(item for item in public["candidate_models"] if item["id"] == "nano-banana-pro")
    assert _ratio_field(candidate["ui_schema"])["required"] is True
    assert "auto" not in _ratio_field(candidate["ui_schema"])["suggestions"]
    assert "aspect_ratio" not in candidate["ui_schema"]["defaults"]
    assert payload == original


def _workflow_step(ratio: str = "auto") -> dict:
    return {
        "id": "prepare_photo", "kind": "image", "title": "Prepare photo",
        "instructions": "Choose a format", "model_id": "nano-banana-2-lite",
        "model_title": "Nano Banana 2 Lite", "prompt": "A portrait", "inputs": [],
        "parameters": {"aspect_ratio": ratio},
    }


def test_workflow_ratio_override_replaces_old_auto_and_preserves_snapshot() -> None:
    step = _workflow_step()
    _prompt, parameters = TrendWorkflowService._step_request({}, step, {"aspect_ratio": "9:16"})
    assert parameters["aspect_ratio"] == "9:16"
    assert step["parameters"]["aspect_ratio"] == "auto"


@pytest.mark.parametrize("workflow_request", [{}, {"aspect_ratio": "AUTO"}, {"aspect_ratio": "22:7"}])
def test_workflow_runtime_rejects_missing_or_invalid_ratio(workflow_request: dict) -> None:
    with pytest.raises(TrendWorkflowError, match="[Aa]spect ratio|соотношение сторон"):
        TrendWorkflowService._step_request({}, _workflow_step(), workflow_request)


def test_workflow_step_metadata_exposes_choices_without_auto() -> None:
    presentation = TrendWorkflowService._step_presentation(_workflow_step())
    assert presentation["aspect_ratio_required"] is True
    assert presentation["default_aspect_ratio"] is None
    assert "1:1" in presentation["aspect_ratio_options"]
    assert "auto" not in presentation["aspect_ratio_options"]
    assert "aspect_ratio" not in presentation["settings_summary"]


def test_kling_workflow_frame_step_does_not_offer_unusable_ratio_override() -> None:
    step = {
        **_workflow_step("16:9"), "kind": "video", "model_id": "kling-3.0",
        "parameters": {"duration": 5, "mode": "pro"},
        "bindings": [{"from": "photo.output_image", "to": "image_urls"}],
    }
    presentation = TrendWorkflowService._step_presentation(step)
    assert presentation["aspect_ratio_options"] == []
    assert presentation["aspect_ratio_required"] is False
    assert presentation["default_aspect_ratio"] is None
    _prompt, parameters = TrendWorkflowService._step_request({}, step, {}, input_url="https://cdn.example/frame.jpg")
    assert "aspect_ratio" not in parameters
    with pytest.raises(TrendWorkflowError, match="Unsupported aspect ratio"):
        TrendWorkflowService._step_request({}, step, {"aspect_ratio": "16:9"}, input_url="https://cdn.example/frame.jpg")


async def test_trend_legacy_auto_remains_structurally_readable() -> None:
    spec, clean, *_ = await TrendService._prepare_recipe(
        object(), {"model_id": "nano-banana-2-lite", "video_reference_count": 0},
        model_id="nano-banana-2-lite", prompt="A portrait", parameters={"aspect_ratio": "auto"},
    )
    assert spec.id == "nano-banana-2-lite"
    assert clean["aspect_ratio"] == "auto"


async def test_workflow_legacy_auto_catalog_preview_remains_readable() -> None:
    step = _workflow_step()
    recipe = {
        "steps": [step], "description": "", "preview_url": "https://cdn.example/preview.jpg",
        "workflow_type": "sequential_photo_video", "pricing_source": "generation_service_catalog",
        "tags": [], "usage_count": 0, "sort_order": 0,
    }
    item = SimpleNamespace(id=uuid4(), title="Legacy workflow", created_at=SimpleNamespace(isoformat=lambda: "2026-10-29T00:00:00Z"))
    view = await TrendWorkflowService.public_trend_view(object(), item, recipe)
    assert view["steps"][0]["aspect_ratio_required"] is True
    assert Decimal(view["cost_credits"]) > 0


async def test_workflow_reload_reports_actual_selected_ratio_without_mutating_recipe(monkeypatch: pytest.MonkeyPatch) -> None:
    step = _workflow_step("1:1")
    recipe = {"steps": [step], "preview_url": "https://cdn.example/preview.jpg"}
    run = SimpleNamespace(id=uuid4(), trend_id=uuid4(), recipe_snapshot=recipe, status="running", recipe_version=2)
    generation = _legacy_generation()
    generation.status = "queued"
    generation.parameters = {"_model_id": step["model_id"], "aspect_ratio": "9:16"}
    row = SimpleNamespace(
        id=uuid4(), step_key=step["id"], kind="image", generation_id=generation.id,
        reserved_generation_id=None, media_asset_id=None, status="queued", command_key="selected-frame",
        attempts=1, attempt_history=[],
    )
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [row])),
        get=AsyncMock(return_value=generation),
    )
    monkeypatch.setattr(TrendWorkflowService, "_owned_run", AsyncMock(return_value=run))
    monkeypatch.setattr(MediaAssetService, "ready_assets_for_generations", AsyncMock(return_value={}))
    view = await TrendWorkflowService.public_view(session, run_id=run.id, user_id=generation.user_id)
    assert view["steps"][0]["settings_summary"]["aspect_ratio"] == "9:16"
    assert view["steps"][0]["default_aspect_ratio"] == "9:16"
    assert step["parameters"]["aspect_ratio"] == "1:1"
    session.get.assert_awaited_once_with(Generation, generation.id)


async def test_workflow_photo_quote_does_not_bypass_admission_when_check_ready_is_false() -> None:
    with pytest.raises(TrendWorkflowError, match="[Aa]spect ratio|соотношение сторон"):
        await TrendWorkflowService.quote_for_step(
            object(), {}, _workflow_step(), user_id=None, request={}, check_ready=False,
        )


async def test_template_future_video_slots_do_not_bypass_fixed_audio_validation() -> None:
    audio = SimpleNamespace(
        status="ready", probe_status="ready", duration_ms=31_000, size_bytes=1_000,
        source_url="https://cdn.example/fixed-audio.mp3",
    )
    session = SimpleNamespace(
        info={}, scalar=AsyncMock(return_value=audio),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [audio])),
    )
    with pytest.raises(InvalidModelParametersError, match="audio.*30 seconds"):
        await TrendService._prepare_recipe(
            session, {"model_id": "seedance-2.5", "video_reference_count": 1},
            model_id="seedance-2.5", prompt="Animate @Video1 with @Audio1",
            parameters={
                "duration": 5, "resolution": "720p", "aspect_ratio": "9:16",
                "reference_video_urls": ["https://example.invalid/future-slot.mp4"],
                "reference_audio_urls": [audio.source_url],
            },
        )
