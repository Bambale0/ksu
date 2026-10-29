from __future__ import annotations

import random
from decimal import Decimal
import pytest
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.services.generations import GenerationService
from app.services.trends import TrendService
from app.services.trend_workflows import TrendWorkflowConflict, TrendWorkflowError, TrendWorkflowService, _hash_payload
from app.api.v1.trends import (
    _command_key,
    create_trend_workflow,
    run_trend_workflow_step,
    TrendWorkflowRequest,
    TrendWorkflowStepRequest,
)
from fastapi import HTTPException
from app.services.generation_provider import GenerationProviderService
from app.core.config import settings
from app.db.admin_models import AdminTrend
from app.db.models import AdminAccount, Generation, User, Wallet, WalletTransaction
from app.db.session import SessionFactory
from app.db.trend_workflow_models import TrendWorkflowStep


def _v2_payload() -> dict[str, object]:
    return {
        "schema_version": 2,
        "workflow_type": "sequential_photo_video",
        "preview_url": "https://cdn.example.invalid/photo-video.jpg",
        "steps": [
            {
                "id": "prepare_photo",
                "kind": "image",
                "title": "Prepare photo",
                "instructions": "Create the outfit photo.",
                "model_id": "nano-banana-pro",
                "prompt": "Create the requested outfit photo.",
                "parameters": {"aspect_ratio": "1:1", "resolution": "1K"},
                "inputs": [
                    {
                        "id": "person_photo",
                        "label": "Your photo",
                        "help": "A clear face photo.",
                        "type": "image",
                        "required": True,
                        "order": 0,
                    },
                ],
            },
            {
                "id": "animate_photo",
                "kind": "video",
                "title": "Animate photo",
                "instructions": "Animate the prepared photo.",
                "model_id": "wan-2.7-i2v",
                "prompt": "Animate the prepared photo.",
                "parameters": {
                    "duration": 5,
                    "resolution": "720p",
                    "aspect_ratio": "16:9",
                },
                "inputs": [],
                "bindings": [
                    {
                        "from": "prepare_photo.output_image",
                        "to": "first_frame_url",
                    },
                ],
            },
        ],
    }


def test_v2_recipe_normalizes_two_ordered_steps_and_explicit_output_binding() -> None:
    recipe = TrendService.normalize_recipe("Photo then video", _v2_payload())

    assert recipe["schema_version"] == 2
    assert recipe["workflow_type"] == "sequential_photo_video"
    assert [step["kind"] for step in recipe["steps"]] == ["image", "video"]
    assert recipe["steps"][1]["bindings"] == [
        {"from": "prepare_photo.output_image", "to": "first_frame_url"}
    ]


def test_v2_recipe_preserves_separate_safe_step_preview_urls() -> None:
    payload = _v2_payload()
    payload["steps"][0]["preview_url"] = "https://cdn.example.invalid/step-1.jpg"
    payload["steps"][1]["preview_url"] = "https://cdn.example.invalid/step-2.jpg"

    recipe = TrendService.normalize_recipe("Photo then video", payload)

    assert [step["preview_url"] for step in recipe["steps"]] == [
        "https://cdn.example.invalid/step-1.jpg",
        "https://cdn.example.invalid/step-2.jpg",
    ]


def test_v2_recipe_rejects_unsafe_step_preview_url() -> None:
    payload = _v2_payload()
    payload["steps"][0]["preview_url"] = "javascript:alert(1)"

    with pytest.raises(TrendWorkflowError, match="preview_url"):
        TrendService.normalize_recipe("Unsafe preview", payload)


def test_v2_recipe_rejects_misordered_steps_before_persistence() -> None:
    payload = _v2_payload()
    payload["steps"] = list(reversed(payload["steps"]))

    with pytest.raises(ValueError, match="image step must precede video step"):
        TrendService.normalize_recipe("Invalid order", payload)


def test_v2_recipe_rejects_gapped_image_placeholders_and_wrong_binding_field() -> None:
    payload = _v2_payload()
    payload["steps"][0]["prompt"] = "Use @Image1 and @Image3."
    with pytest.raises(TrendWorkflowError, match="numbered consecutively"):
        TrendService.normalize_recipe("Invalid placeholders", payload)

    payload = _v2_payload()
    payload["steps"][1]["bindings"][0]["to"] = "provider_private_url"
    with pytest.raises(TrendWorkflowError, match="binding target"):
        TrendService.normalize_recipe("Invalid binding", payload)


def test_v2_recipe_rejects_non_i2v_video_operation_even_when_field_is_known() -> None:
    payload = _v2_payload()
    payload["steps"][1]["model_id"] = "wan-2.7-video-edit"
    payload["steps"][1]["bindings"][0]["to"] = "reference_image"

    with pytest.raises(TrendWorkflowError, match="image-to-video"):
        TrendService.normalize_recipe("Edit is not i2v", payload)


def test_v2_slots_normalize_select_options_and_reject_optional_image_holes() -> None:
    payload = _v2_payload()
    payload["steps"][0]["inputs"] = [
        {
            "id": "optional_style",
            "label": "Optional style",
            "help": "Optional style reference.",
            "type": "image",
            "required": False,
            "order": 0,
        },
        {
            "id": "person_photo",
            "label": "Your photo",
            "help": "A clear face photo.",
            "type": "image",
            "required": True,
            "order": 1,
        },
    ]
    payload["steps"][0]["prompt"] = "Use @Image1 and @Image2."
    with pytest.raises(TrendWorkflowError, match="optional image"):
        TrendService.normalize_recipe("No optional hole", payload)

    payload = _v2_payload()
    payload["steps"][0]["inputs"] = [
        {
            "id": "style",
            "label": "Style",
            "help": "Choose a style.",
            "type": "select",
            "required": True,
            "order": 0,
            "options": ["editorial", "casual"],
        },
            {**payload["steps"][0]["inputs"][0], "order": 1},
    ]
    recipe = TrendService.normalize_recipe("Typed options", payload)
    assert recipe["steps"][0]["inputs"][0]["options"] == ["editorial", "casual"]


@pytest.mark.asyncio
async def test_public_v2_view_quotes_required_image_with_safe_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    item = SimpleNamespace(id=uuid4(), title="Photo then video", created_at=SimpleNamespace(isoformat=lambda: "now"))
    recipe = TrendWorkflowService.normalize_recipe(item.title, _v2_payload())
    seen: list[dict[str, object]] = []

    async def prepare(_session, **kwargs):
        seen.append(kwargs)
        return (None, {}, 1, None, 1)

    monkeypatch.setattr(GenerationService, "prepare_template_request", prepare)
    view = await TrendWorkflowService.public_trend_view(AsyncMock(), item, recipe)

    assert len(view["steps"]) == 2
    assert seen[0]["parameters"]["image_input"] == ["https://example.invalid/workflow-public-image-1.jpg"]
    assert "person_photo" not in seen[0]["parameters"]


@pytest.mark.asyncio
@pytest.mark.parametrize("video_url", [
    "https://cdn.example.invalid/step-2.mp4?version=1",
    "https://cdn.example.invalid/step-2.MOV",
])
async def test_v2_video_step_preview_is_preserved_as_display_only_media(
    monkeypatch: pytest.MonkeyPatch, video_url: str,
) -> None:
    payload = _v2_payload()
    payload["steps"][0]["preview_url"] = "https://cdn.example.invalid/step-1.jpg"
    payload["steps"][1]["preview_url"] = video_url
    item = SimpleNamespace(id=uuid4(), title="Video step preview", created_at=SimpleNamespace(isoformat=lambda: "now"))
    recipe = TrendService.normalize_recipe(item.title, payload)
    prepared: list[dict[str, object]] = []

    async def prepare(_session, **kwargs):
        prepared.append(kwargs)
        return (None, {}, 1, None, 1)

    monkeypatch.setattr(GenerationService, "prepare_template_request", prepare)
    view = await TrendWorkflowService.public_trend_view(AsyncMock(), item, recipe)

    assert recipe["steps"][1]["preview_url"] == video_url
    assert recipe["steps"][1]["parameters"] == payload["steps"][1]["parameters"]
    assert recipe["steps"][1]["bindings"] == payload["steps"][1]["bindings"]
    assert [step["preview_url"] for step in view["steps"]] == [
        "https://cdn.example.invalid/step-1.jpg", video_url,
    ]
    assert all("prompt" not in step and "parameters" not in step for step in view["steps"])
    assert prepared
    assert all("preview_url" not in request["parameters"] for request in prepared)


def test_workflow_command_key_is_required_for_paid_start_and_run() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _command_key(None, required=True)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_workflow_create_route_rejects_missing_idempotency_before_service(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AsyncMock()
    monkeypatch.setattr(TrendWorkflowService, "create_or_resume", service)
    with pytest.raises(HTTPException) as exc_info:
        await create_trend_workflow(
            uuid4(), TrendWorkflowRequest(), SimpleNamespace(id=uuid4()), AsyncMock(), Mock(), None,
        )
    assert exc_info.value.status_code == 400
    service.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_v1_run_rejects_v2_before_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    item = SimpleNamespace(id=uuid4(), is_active=True, title="Photo then video", payload=_v2_payload())
    session = AsyncMock()
    session.get.return_value = item
    create = AsyncMock()
    monkeypatch.setattr(GenerationService, "create", create)

    with pytest.raises(ValueError, match="sequential workflow API"):
        await TrendService.run(
            session,
            AsyncMock(),
            user_id=uuid4(),
            trend_id=item.id,
            reference_urls=[],
        )
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_step2_ready_owned_image_gate_runs_before_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    step = SimpleNamespace(
        id=uuid4(), workflow_id=run_id, step_key="animate_photo", kind="video", ordinal=1,
        status="pending", generation_id=None, media_asset_id=None, attempts=0,
        command_key=None, payload_hash=None,
    )
    run = SimpleNamespace(id=run_id, trend_id=uuid4(), usage_incremented=True, user_id=uuid4(), recipe_snapshot=_v2_payload(), status="created")
    monkeypatch.setattr(TrendWorkflowService, "_owned_step", AsyncMock(return_value=(run, step)))
    monkeypatch.setattr(
        TrendWorkflowService,
        "_ready_step1_asset",
        AsyncMock(side_effect=TrendWorkflowError("Step 2 requires a ready owned image")),
    )
    create = AsyncMock()
    monkeypatch.setattr(GenerationService, "create", create)

    with pytest.raises(TrendWorkflowError, match="ready owned image"):
        await TrendWorkflowService.run_step(
            AsyncMock(),
            AsyncMock(),
            run_id=run_id,
            step_key="animate_photo",
            user_id=run.user_id,
            command_key="video-command",
            request={"reference_urls": [], "values": {}, "quoted_cost_rox": "0.00"},
        )
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_step_command_replays_without_second_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    request = {"reference_urls": [], "values": {"person_photo": "not-used"}, "quoted_cost_rox": "0.00"}
    step = SimpleNamespace(
        id=uuid4(), workflow_id=run_id, step_key="prepare_photo", kind="image", ordinal=0,
        status="queued", generation_id=uuid4(), media_asset_id=None, attempts=1,
        command_key="photo-command", payload_hash=_hash_payload(request),
    )
    run = SimpleNamespace(id=run_id, trend_id=uuid4(), usage_incremented=True, user_id=uuid4(), recipe_snapshot=_v2_payload(), status="running")
    monkeypatch.setattr(TrendWorkflowService, "_owned_step", AsyncMock(return_value=(run, step)))
    create = AsyncMock()
    monkeypatch.setattr(GenerationService, "create", create)

    returned = await TrendWorkflowService.run_step(
        AsyncMock(),
        AsyncMock(),
        run_id=run_id,
        step_key="prepare_photo",
        user_id=run.user_id,
        command_key="photo-command",
        request=request,
    )

    assert returned is step
    create.assert_not_awaited()
    assert step.attempts == 1


@pytest.mark.asyncio
async def test_changed_step_body_replay_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    original = {"reference_urls": [], "values": {}, "quoted_cost_rox": "0.00"}
    step = SimpleNamespace(
        id=uuid4(), workflow_id=run_id, step_key="prepare_photo", kind="image", ordinal=0,
        status="queued", generation_id=uuid4(), media_asset_id=None, attempts=1,
        command_key="photo-command", payload_hash=_hash_payload(original),
    )
    run = SimpleNamespace(id=run_id, trend_id=uuid4(), usage_incremented=True, user_id=uuid4(), recipe_snapshot=_v2_payload(), status="running")
    monkeypatch.setattr(TrendWorkflowService, "_owned_step", AsyncMock(return_value=(run, step)))

    with pytest.raises(TrendWorkflowConflict, match="different request"):
        await TrendWorkflowService.run_step(
            AsyncMock(),
            AsyncMock(),
            run_id=run_id,
            step_key="prepare_photo",
            user_id=run.user_id,
            command_key="photo-command",
            request={"reference_urls": [], "values": {"person_photo": "changed"}, "quoted_cost_rox": "0.00"},
        )


@pytest.mark.asyncio
async def test_workflow_state_creation_preserves_usage_until_first_accepted_generation() -> None:
    item = SimpleNamespace(id=uuid4(), title="Photo then video", is_active=True, payload=_v2_payload())
    item.payload["usage_count"] = 7
    session = AsyncMock()
    session.scalar = AsyncMock(side_effect=[None, item, item])
    session.add = Mock()

    request = {"reference_urls": [], "values": {}}
    first = await TrendWorkflowService.create_or_resume(
        session,
        user_id=uuid4(),
        trend_id=item.id,
        command_key="start-command",
        request=request,
    )

    assert first.usage_incremented is False
    assert item.payload["usage_count"] == 7
    assert session.add.call_count == 3
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_image_step_does_not_require_image_as_text_value() -> None:
    recipe = TrendWorkflowService.normalize_recipe("Image input", _v2_payload())
    prompt, parameters = TrendWorkflowService._step_request(
        recipe,
        recipe["steps"][0],
        {"reference_urls": ["https://owned.invalid/photo.jpg"], "values": {}},
    )
    assert prompt
    assert parameters["image_input"] == ["https://owned.invalid/photo.jpg"]


def test_image_inputs_are_bound_to_semantic_slots() -> None:
    recipe = TrendWorkflowService.normalize_recipe("Image input", _v2_payload())
    _prompt, parameters = TrendWorkflowService._step_request(
        recipe,
        recipe["steps"][0],
        {
            "image_inputs": [{"slot_id": "person_photo", "url": "https://owned.invalid/photo.jpg"}],
            "values": {},
        },
    )
    assert parameters["image_input"] == ["https://owned.invalid/photo.jpg"]

    with pytest.raises(TrendWorkflowError, match="unknown or duplicate"):
        TrendWorkflowService._step_request(
            recipe,
            recipe["steps"][0],
            {"image_inputs": [{"slot_id": "other", "url": "https://owned.invalid/photo.jpg"}], "values": {}},
        )


def test_admin_metadata_update_preserves_v2_structure_and_rejects_downconversion() -> None:
    existing = _v2_payload()
    merged = TrendWorkflowService.merge_admin_payload(existing, {"description": "Updated copy"})
    assert merged["steps"] == existing["steps"]
    assert merged["description"] == "Updated copy"
    with pytest.raises(TrendWorkflowError, match="downconverted"):
        TrendWorkflowService.merge_admin_payload(existing, {"schema_version": 1})


@pytest.mark.asyncio
async def test_generation_fk_is_linked_after_generation_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    step = SimpleNamespace(
        id=uuid4(), workflow_id=run_id, step_key="prepare_photo", kind="image", ordinal=0,
        status="pending", generation_id=None, media_asset_id=None, attempts=0,
        command_key=None, payload_hash=None, reserved_generation_id=None, attempt_history=[],
    )
    run = SimpleNamespace(id=run_id, trend_id=uuid4(), usage_incremented=True, user_id=uuid4(), recipe_snapshot=_v2_payload(), status="created")
    monkeypatch.setattr(TrendWorkflowService, "_owned_step", AsyncMock(return_value=(run, step)))
    session = AsyncMock()
    session.get.return_value = None
    generation = SimpleNamespace(id=uuid4(), status="queued", parameters={})

    async def create(*_args, **_kwargs):
        assert step.generation_id is None
        assert step.reserved_generation_id is not None
        return generation

    monkeypatch.setattr(GenerationService, "create", create)
    result = await TrendWorkflowService.run_step(
        session, AsyncMock(), run_id=run_id, step_key="prepare_photo", user_id=run.user_id,
        command_key="photo-a", request={"reference_urls": ["https://owned.invalid/photo.jpg"], "values": {}, "quoted_cost_rox": "12.00"},
    )
    assert result.generation_id == generation.id
    assert result.reserved_generation_id is None


@pytest.mark.asyncio
async def test_same_command_reconciles_committed_generation_reservation(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    generation_id = uuid4()
    request = {
        "reference_urls": ["https://owned.invalid/photo.jpg"],
        "values": {},
        "quoted_cost_rox": "12.00",
    }
    step = SimpleNamespace(
        id=uuid4(), workflow_id=run_id, step_key="prepare_photo", kind="image", ordinal=0,
        status="queued", generation_id=None, media_asset_id=None, attempts=1,
        command_key="photo-a", payload_hash=_hash_payload(request),
        reserved_generation_id=generation_id, attempt_history=[],
    )
    run = SimpleNamespace(id=run_id, trend_id=uuid4(), usage_incremented=True, user_id=uuid4(), recipe_snapshot=_v2_payload(), status="running")
    generation = SimpleNamespace(id=generation_id, user_id=run.user_id, status="queued", error=None)
    monkeypatch.setattr(TrendWorkflowService, "_owned_step", AsyncMock(return_value=(run, step)))
    session = AsyncMock()
    session.get.return_value = generation
    create = AsyncMock()
    monkeypatch.setattr(GenerationService, "create", create)

    returned = await TrendWorkflowService.run_step(
        session, AsyncMock(), run_id=run_id, step_key="prepare_photo", user_id=run.user_id,
        command_key="photo-a", request=request,
    )

    assert returned is step
    assert step.generation_id == generation_id
    assert step.reserved_generation_id is None
    session.commit.assert_awaited_once()
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_quote_is_rejected_before_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    step = SimpleNamespace(
        id=uuid4(), workflow_id=run_id, step_key="prepare_photo", kind="image", ordinal=0,
        status="pending", generation_id=None, media_asset_id=None, attempts=0,
        command_key=None, payload_hash=None, reserved_generation_id=None, attempt_history=[],
    )
    run = SimpleNamespace(id=run_id, trend_id=uuid4(), usage_incremented=True, user_id=uuid4(), recipe_snapshot=_v2_payload(), status="created")
    monkeypatch.setattr(TrendWorkflowService, "_owned_step", AsyncMock(return_value=(run, step)))
    create = AsyncMock()
    monkeypatch.setattr(GenerationService, "create", create)

    with pytest.raises(TrendWorkflowError, match="quoted_cost_rox is required"):
        await TrendWorkflowService.run_step(
            AsyncMock(), AsyncMock(), run_id=run_id, step_key="prepare_photo", user_id=run.user_id,
            command_key="photo-no-quote", request={"reference_urls": ["https://owned.invalid/photo.jpg"], "values": {}},
        )
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_rejects_missing_quote_before_billing(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AsyncMock()
    monkeypatch.setattr(TrendWorkflowService, "run_step", service)
    with pytest.raises(HTTPException) as exc_info:
        await run_trend_workflow_step(
            uuid4(), "prepare_photo", TrendWorkflowStepRequest(), Mock(),
            SimpleNamespace(id=uuid4()), AsyncMock(), AsyncMock(), "run-command",
        )
    assert exc_info.value.status_code == 422
    service.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_forwards_explicit_retry_intent_for_paid_photo_redo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_step = AsyncMock()
    monkeypatch.setattr(TrendWorkflowService, "run_step", run_step)
    monkeypatch.setattr(
        TrendWorkflowService,
        "public_view",
        AsyncMock(return_value={"steps": []}),
    )
    request = Mock(headers={"X-Request-Id": "request-redo"})

    await run_trend_workflow_step(
        uuid4(),
        "prepare_photo",
        TrendWorkflowStepRequest(quoted_cost_rox=Decimal("12.00"), retry=True),
        request,
        SimpleNamespace(id=uuid4()),
        AsyncMock(),
        AsyncMock(),
        "photo-redo-v2",
    )

    forwarded_request = run_step.await_args.kwargs["request"]
    assert forwarded_request["retry"] is True
    assert run_step.await_args.kwargs["command_key"] == "photo-redo-v2"


@pytest.mark.asyncio
async def test_explicit_photo_redo_uses_new_generation_and_preserves_old_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    old_generation = SimpleNamespace(id=uuid4(), user_id=uuid4(), status="succeeded", error=None)
    old_asset_id = uuid4()
    step = SimpleNamespace(
        id=uuid4(), workflow_id=run_id, step_key="prepare_photo", kind="image", ordinal=0,
        status="ready", generation_id=old_generation.id, media_asset_id=old_asset_id, attempts=1,
        command_key="photo-a", payload_hash=_hash_payload({"reference_urls": ["https://owned.invalid/a.jpg"], "values": {}, "quoted_cost_rox": "12.00"}),
        reserved_generation_id=None, attempt_history=[],
    )
    run = SimpleNamespace(id=run_id, trend_id=uuid4(), usage_incremented=True, user_id=old_generation.user_id, recipe_snapshot=_v2_payload(), status="step1_ready")
    monkeypatch.setattr(TrendWorkflowService, "_owned_step", AsyncMock(return_value=(run, step)))
    session = AsyncMock()
    session.scalar.return_value = None
    session.get.return_value = old_generation
    new_generation = SimpleNamespace(id=uuid4(), status="queued", parameters={})
    monkeypatch.setattr(GenerationService, "create", AsyncMock(return_value=new_generation))

    await TrendWorkflowService.run_step(
        session, AsyncMock(), run_id=run_id, step_key="prepare_photo", user_id=run.user_id,
        command_key="photo-redo", request={
            "reference_urls": ["https://owned.invalid/b.jpg"], "values": {},
            "quoted_cost_rox": "12.00", "retry": True,
        },
    )

    assert step.generation_id == new_generation.id
    assert step.media_asset_id is None
    assert step.attempt_history[0]["generation_id"] == str(old_generation.id)
    assert step.attempt_history[0]["media_asset_id"] == str(old_asset_id)


@pytest.mark.asyncio
async def test_existing_run_replays_after_template_is_deactivated(monkeypatch: pytest.MonkeyPatch) -> None:
    trend_id = uuid4()
    user_id = uuid4()
    request = {"reference_urls": [], "values": {}}
    existing = SimpleNamespace(request_hash=_hash_payload(request))
    session = AsyncMock()
    session.scalar.return_value = existing

    result = await TrendWorkflowService.create_or_resume(
        session, user_id=user_id, trend_id=trend_id, command_key="start-a", request=request,
    )

    assert result is existing
    session.add.assert_not_called()


def test_nontrivial_image_layout_requires_semantic_slots() -> None:
    payload = _v2_payload()
    payload["steps"][0]["inputs"] = [
        {**payload["steps"][0]["inputs"][0], "id": "person_photo"},
        {
            "id": "style_reference", "label": "Style reference", "help": "Optional style image.",
            "type": "image", "required": False, "order": 1,
        },
    ]
    recipe = TrendWorkflowService.normalize_recipe("Semantic images", payload)

    with pytest.raises(TrendWorkflowError, match="image_inputs with slot_id"):
        TrendWorkflowService._step_request(
            recipe, recipe["steps"][0],
            {"reference_urls": ["https://owned.invalid/photo.jpg"], "values": {}},
        )


@pytest.mark.asyncio
async def test_unresolved_reservation_is_publicly_safe_reconcile_state(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    step = SimpleNamespace(
        id=uuid4(), workflow_id=run_id, step_key="prepare_photo", kind="image", ordinal=0,
        status="queued", generation_id=None, media_asset_id=None, attempts=1,
        reserved_generation_id=uuid4(), attempt_history=[], command_key="unresolved-command",
    )
    run = SimpleNamespace(id=run_id, user_id=uuid4(), trend_id=uuid4(), recipe_version=2,
                          recipe_snapshot=_v2_payload(), status="running")
    session = AsyncMock()
    session.scalar.return_value = run
    session.scalars.return_value = SimpleNamespace(all=lambda: [step])
    session.get.return_value = None
    monkeypatch.setattr(
        "app.services.media_assets.MediaAssetService.ready_assets_for_generations",
        AsyncMock(return_value={}),
    )

    view = await TrendWorkflowService.public_view(session, run_id=run_id, user_id=run.user_id)
    assert view["steps"][0]["command_id"] == "unresolved-command"
    assert view["steps"][0]["generation_id"] is None

    assert view["status"] == "reconciling"
    assert view["steps"][0]["reconcile_required"] is True


def test_pricing_source_is_explicitly_catalog_derived() -> None:
    recipe = TrendWorkflowService.normalize_recipe("Catalog pricing", _v2_payload())
    assert recipe["pricing_source"] == "generation_service_catalog"


@pytest.mark.asyncio
async def test_run_carries_quote_into_generation_debit_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    step = SimpleNamespace(
        id=uuid4(), workflow_id=run_id, step_key="prepare_photo", kind="image", ordinal=0,
        status="pending", generation_id=None, media_asset_id=None, attempts=0,
        command_key=None, payload_hash=None, reserved_generation_id=None, attempt_history=[],
    )
    run = SimpleNamespace(id=run_id, trend_id=uuid4(), usage_incremented=True, user_id=uuid4(), recipe_snapshot=_v2_payload(), status="created")
    monkeypatch.setattr(TrendWorkflowService, "_owned_step", AsyncMock(return_value=(run, step)))
    session = AsyncMock()
    session.get.return_value = None
    captured: dict[str, object] = {}

    async def create(*_args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=uuid4(), status="queued", parameters={})

    monkeypatch.setattr(GenerationService, "create", create)
    await TrendWorkflowService.run_step(
        session, AsyncMock(), run_id=run_id, step_key="prepare_photo", user_id=run.user_id,
        command_key="photo-quoted", request={
            "reference_urls": ["https://owned.invalid/photo.jpg"],
            "values": {},
            "quoted_cost_rox": "12.00",
        },
    )
    assert captured["expected_cost_rox"] == "12.00"


@pytest.mark.asyncio
async def test_workflow_generation_joins_existing_transaction_before_linking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The workflow FK link must be committed with generation billing."""
    run_id = uuid4()
    step = SimpleNamespace(
        id=uuid4(), workflow_id=run_id, step_key="prepare_photo", kind="image", ordinal=0,
        status="pending", generation_id=None, media_asset_id=None, attempts=0,
        command_key=None, payload_hash=None, reserved_generation_id=None, attempt_history=[],
    )
    run = SimpleNamespace(id=run_id, trend_id=uuid4(), usage_incremented=True, user_id=uuid4(), recipe_snapshot=_v2_payload(), status="created")
    monkeypatch.setattr(TrendWorkflowService, "_owned_step", AsyncMock(return_value=(run, step)))
    session = AsyncMock()
    generation = SimpleNamespace(id=uuid4(), status="queued", user_id=run.user_id, parameters={})
    captured: dict[str, object] = {}

    async def create(*_args: object, **kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return generation

    monkeypatch.setattr(GenerationService, "create", create)
    redis = AsyncMock()
    commit_observations: list[int] = []

    async def commit() -> None:
        commit_observations.append(redis.rpush.await_count)

    session.commit.side_effect = commit
    await TrendWorkflowService.run_step(
        session,
        redis,
        run_id=run_id,
        step_key="prepare_photo",
        user_id=run.user_id,
        command_key="photo-transaction",
        request={
            "reference_urls": ["https://owned.invalid/photo.jpg"],
            "values": {},
            "quoted_cost_rox": "12.00",
        },
    )

    assert captured["commit"] is False
    assert captured["wake"] is False
    assert step.generation_id == generation.id
    assert step.reserved_generation_id is None
    session.commit.assert_awaited_once()
    assert commit_observations == [0]
    redis.rpush.assert_awaited_once_with(GenerationService.WAKE_KEY, str(generation.id))


@pytest.mark.asyncio
async def test_explicit_retry_keeps_attempt_history_and_rejects_replay_of_old_key(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    old_generation = SimpleNamespace(id=uuid4(), status="failed", error="provider failed")
    step = SimpleNamespace(
        id=uuid4(), workflow_id=run_id, step_key="prepare_photo", kind="image", ordinal=0,
        status="queued", generation_id=old_generation.id, media_asset_id=None, attempts=1,
        command_key="photo-a", payload_hash=_hash_payload({"reference_urls": ["https://owned.invalid/a.jpg"], "values": {}, "quoted_cost_rox": "12.00"}),
        reserved_generation_id=None, attempt_history=[],
    )
    run = SimpleNamespace(id=run_id, trend_id=uuid4(), usage_incremented=True, user_id=uuid4(), recipe_snapshot=_v2_payload(), status="running")
    monkeypatch.setattr(TrendWorkflowService, "_owned_step", AsyncMock(return_value=(run, step)))
    session = AsyncMock()
    session.get.return_value = old_generation
    session.scalar.return_value = None
    new_generation = SimpleNamespace(id=uuid4(), status="queued", parameters={})
    monkeypatch.setattr(GenerationService, "create", AsyncMock(return_value=new_generation))

    request_b = {"reference_urls": ["https://owned.invalid/b.jpg"], "values": {}, "quoted_cost_rox": "12.00", "retry": True}
    await TrendWorkflowService.run_step(
        session, AsyncMock(), run_id=run_id, step_key="prepare_photo", user_id=run.user_id,
        command_key="photo-b", request=request_b,
    )
    assert step.generation_id == new_generation.id
    assert step.attempt_history[0]["command_key"] == "photo-a"

    with pytest.raises(TrendWorkflowConflict, match="previous attempt"):
        await TrendWorkflowService.run_step(
            session, AsyncMock(), run_id=run_id, step_key="prepare_photo", user_id=run.user_id,
            command_key="photo-a", request={"reference_urls": ["https://owned.invalid/a.jpg"], "values": {}, "quoted_cost_rox": "12.00"},
        )


@pytest.mark.asyncio
async def test_provider_submission_resolves_fresh_owned_media_url(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PIL import Image
    from app.services.local_media_storage import LOCAL_MEDIA_BUCKET

    monkeypatch.setenv("MEDIA_LOCAL_ROOT", str(tmp_path))
    Image.new("RGB", (2, 2)).save(tmp_path / "asset.png")
    owner_id = uuid4()
    asset = SimpleNamespace(id=uuid4(), user_id=owner_id, status="ready", object_key="asset.png", bucket=LOCAL_MEDIA_BUCKET)
    session = AsyncMock()
    session.scalar.return_value = asset
    monkeypatch.setattr("app.services.media_assets.MediaAssetService.provider_source_url", lambda _asset: "https://fresh.invalid/signed.png")
    generation = SimpleNamespace(user_id=owner_id)
    payload = {"first_frame_url": f"ksu-media://{asset.id}", "prompt": "safe"}

    resolved = await GenerationProviderService._resolve_workflow_media_input(session, generation, payload)
    assert resolved["first_frame_url"] == "https://fresh.invalid/signed.png"


def test_migration_downgrade_has_live_state_guard() -> None:
    source = open("alembic/versions/0044_trend_workflows.py", encoding="utf-8").read()
    assert "Refusing to downgrade while trend workflow state exists" in source
    assert "SELECT EXISTS" in source


async def _real_workflow_fixture(label: str) -> tuple[UUID, UUID, UUID]:
    async with SessionFactory() as session:
        user = User(
            telegram_id=random.randrange(7_000_000_000_000, 7_999_999_999_999),
            first_name="Synthetic workflow user",
        )
        admin_user = User(
            telegram_id=random.randrange(7_000_000_000_000, 7_999_999_999_999),
            first_name="Synthetic workflow admin",
        )
        session.add_all([user, admin_user])
        await session.flush()
        admin = AdminAccount(user_id=admin_user.id, role="admin")
        session.add(admin)
        await session.flush()
        trend = AdminTrend(
            title=label,
            payload=_v2_payload(),
            is_active=True,
            created_by_admin_id=admin.id,
        )
        session.add_all([trend, Wallet(user_id=user.id, balance=Decimal("1000.00"))])
        await session.commit()
        run = await TrendWorkflowService.create_or_resume(
            session,
            user_id=user.id,
            trend_id=trend.id,
            command_key=str(uuid4()),
            request={},
        )
        return user.id, trend.id, run.id


@pytest.mark.asyncio
async def test_postgres_crash_recovery_links_reserved_paid_generation_before_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A committed generation can never remain paid but unlinked to its step."""
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    user_id, _trend_id, run_id = await _real_workflow_fixture("Synthetic crash recovery")
    request = {"reference_urls": ["https://example.invalid/synthetic.jpg"], "values": {}}
    async with SessionFactory() as session:
        quote = await TrendWorkflowService.quote_step(
            session, run_id=run_id, step_key="prepare_photo", user_id=user_id, request=request,
        )
    request["quoted_cost_rox"] = quote["cost_rox"]

    async with SessionFactory() as session:
        step = await session.scalar(
            select(TrendWorkflowStep).where(
                TrendWorkflowStep.workflow_id == run_id,
                TrendWorkflowStep.step_key == "prepare_photo",
            )
        )
        assert step is not None
        generation_id = uuid4()
        step.command_key = "crash-after-debit"
        step.payload_hash = _hash_payload(request)
        step.attempts = 1
        step.status = "queued"
        step.reserved_generation_id = generation_id
        await session.commit()

    redis = AsyncMock()
    async with SessionFactory() as session:
        await GenerationService.create(
            session,
            redis,
            user_id=user_id,
            model_id="nano-banana-pro",
            prompt="Create the requested outfit photo.",
            parameters={"image_input": [request["reference_urls"][0]]},
            action_type="trend",
            generation_id=generation_id,
            expected_cost_rox=request["quoted_cost_rox"],
        )

    async with SessionFactory() as session:
        replay = await TrendWorkflowService.run_step(
            session,
            redis,
            run_id=run_id,
            step_key="prepare_photo",
            user_id=user_id,
            command_key="crash-after-debit",
            request=request,
        )
        view = await TrendWorkflowService.public_view(session, run_id=run_id, user_id=user_id)
        generation_count = await session.scalar(
            select(func.count()).select_from(Generation).where(Generation.user_id == user_id)
        )
        transaction_count = await session.scalar(
            select(func.count()).select_from(WalletTransaction).where(WalletTransaction.user_id == user_id)
        )

    assert replay.generation_id == generation_id
    assert replay.reserved_generation_id is None
    assert view["steps"][0]["generation_id"] == str(generation_id)
    assert generation_count == 1
    assert transaction_count == 1


@pytest.mark.asyncio
async def test_postgres_missing_workflow_quote_does_not_create_or_debit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    user_id, _trend_id, run_id = await _real_workflow_fixture("Synthetic missing quote")
    redis = AsyncMock()
    request = {"reference_urls": ["https://example.invalid/synthetic.jpg"], "values": {}}

    with pytest.raises(TrendWorkflowError, match="quoted_cost_rox is required"):
        async with SessionFactory() as session:
            await TrendWorkflowService.run_step(
                session,
                redis,
                run_id=run_id,
                step_key="prepare_photo",
                user_id=user_id,
                command_key="missing-quote",
                request=request,
            )

    async with SessionFactory() as session:
        wallet = await session.get(Wallet, user_id)
        generation_count = await session.scalar(
            select(func.count()).select_from(Generation).where(Generation.user_id == user_id)
        )
        transaction_count = await session.scalar(
            select(func.count()).select_from(WalletTransaction).where(WalletTransaction.user_id == user_id)
        )

    assert wallet is not None
    assert wallet.balance == Decimal("1000.00")
    assert generation_count == 0
    assert transaction_count == 0
