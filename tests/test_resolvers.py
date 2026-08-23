"""Unit tests for the capability resolver and post-generation action resolvers."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.db.models import Generation
from app.services.generation_actions import (
    ActionResolveError,
    AnimateResolver,
    EditImageResolver,
    GenerationActionType,
    PublishResolver,
    RemixResolver,
    VariationResolver,
    resolver_for,
)
from app.services.model_capability import (
    MODE_IMAGE_TO_IMAGE,
    MODE_IMAGE_TO_VIDEO,
    ModelCapabilityResolver,
)
from app.services.model_catalog import ModelCatalog


def _generation(*, media_type: str, model_id: str) -> Generation:
    extension = "mp4" if media_type == "video" else "png"
    return Generation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        kind=media_type,
        status="succeeded",
        prompt="portrait in soft light",
        result_url=f"https://cdn.example/result.{extension}",
        cost_rox=Decimal("10.00"),
        parameters={
            "_model_id": model_id,
            "_media_type": media_type,
            "negative_prompt": "blurry",
            "aspect_ratio": "1:1",
            "_internal": "hidden",
        },
    )


# --- ModelCapabilityResolver -------------------------------------------------


def test_supports_mode_matches_operations() -> None:
    edit_spec = ModelCatalog.get("nano-banana-edit")
    t2i_spec = ModelCatalog.get("nano-banana")
    i2v_spec = ModelCatalog.get("grok-video-i2v")

    assert ModelCapabilityResolver.supports(edit_spec, MODE_IMAGE_TO_IMAGE)
    assert not ModelCapabilityResolver.supports(t2i_spec, MODE_IMAGE_TO_IMAGE)
    assert ModelCapabilityResolver.supports(t2i_spec, "text_to_image")
    assert ModelCapabilityResolver.supports(i2v_spec, MODE_IMAGE_TO_VIDEO)
    assert not ModelCapabilityResolver.supports(i2v_spec, MODE_IMAGE_TO_IMAGE)


def test_supports_input_declared_fields_only() -> None:
    assert ModelCapabilityResolver.supports_input(ModelCatalog.get("grok-video-i2v"), "image")
    assert not ModelCapabilityResolver.supports_input(ModelCatalog.get("grok-image-t2i"), "image")
    assert not ModelCapabilityResolver.supports_input(ModelCatalog.get("nano-banana-edit"), "video")


def test_resolve_fallback_edit_prefers_image_edit_operation() -> None:
    fallback = ModelCapabilityResolver.resolve_fallback("image", MODE_IMAGE_TO_IMAGE)
    assert fallback is not None
    assert fallback.media_type == "image"
    assert fallback.operation in {"image_edit", "image_to_image", "generate_or_edit"}


def test_resolve_fallback_animate_returns_i2v_video_model() -> None:
    fallback = ModelCapabilityResolver.resolve_fallback("image", MODE_IMAGE_TO_VIDEO)
    assert fallback is not None
    assert fallback.media_type == "video"
    assert fallback.operation != "video_upscale"


def test_no_compatibilities_for_video_source_edit() -> None:
    # i2i requires an image source; video results have no compatible image edit.
    assert ModelCapabilityResolver.compatible_specs("video", MODE_IMAGE_TO_IMAGE) == []


# --- Resolvers ---------------------------------------------------------------


def test_remix_resolver_copies_intent_without_internal_params() -> None:
    generation = _generation(media_type="image", model_id="nano-banana-pro")
    payload = RemixResolver().resolve(generation)

    assert payload["prompt"] == "portrait in soft light"
    assert payload["negative_prompt"] == "blurry"
    assert payload["model"] == "nano-banana-pro"
    assert "negative_prompt" not in payload["settings"]
    assert all(not key.startswith("_") for key in payload["settings"])


def test_variation_resolver_keeps_model_and_flags_quote() -> None:
    generation = _generation(media_type="image", model_id="nano-banana-pro")
    payload = VariationResolver().resolve(generation)

    assert payload["model"] == "nano-banana-pro"
    assert payload["requires_billing_quote"] is True
    assert payload["deprecated_model"] is False


def test_variation_resolver_marks_unknown_model_deprecated() -> None:
    generation = _generation(media_type="image", model_id="retired-model-x")
    payload = VariationResolver().resolve(generation)
    assert payload["deprecated_model"] is True


def test_edit_resolver_forces_i2i_with_compatible_model() -> None:
    generation = _generation(media_type="image", model_id="nano-banana-pro")
    payload = EditImageResolver().resolve(generation)

    assert payload["mode"] == MODE_IMAGE_TO_IMAGE
    model = ModelCatalog.get(payload["model"])
    assert model.media_type == "image"
    assert payload["source_media"]["url"] == generation.result_url
    assert payload["input_url"] == generation.result_url


def test_edit_resolver_rejects_video_results() -> None:
    generation = _generation(media_type="video", model_id="grok-video-i2v")
    with pytest.raises(ActionResolveError):
        EditImageResolver().resolve(generation)


def test_animate_resolver_forces_i2v_with_video_model() -> None:
    generation = _generation(media_type="image", model_id="nano-banana-pro")
    payload = AnimateResolver().resolve(generation)

    assert payload["mode"] == MODE_IMAGE_TO_VIDEO
    model = ModelCatalog.get(payload["model"])
    assert model.media_type == "video"
    assert payload["source_media"]["type"] == "image"


def test_animate_resolver_rejects_missing_result() -> None:
    generation = _generation(media_type="image", model_id="nano-banana-pro")
    generation.result_url = None
    with pytest.raises(ActionResolveError):
        AnimateResolver().resolve(generation)


def test_publish_resolver_blocks_derivatives() -> None:
    root = _generation(media_type="image", model_id="nano-banana-pro")
    assert PublishResolver().resolve(root)["publishable"] is True

    derivative = _generation(media_type="image", model_id="nano-banana-pro")
    derivative.source_feed_gen_id = uuid.uuid4()
    with pytest.raises(ActionResolveError):
        PublishResolver().resolve(derivative)


# --- Registry ----------------------------------------------------------------


def test_registry_maps_wire_ids_and_aliases() -> None:
    assert resolver_for("remix").action_type == GenerationActionType.REMIX
    assert resolver_for("repeat").action_type == GenerationActionType.VARIATION
    assert resolver_for("new_prompt").action_type == GenerationActionType.VARIATION
    assert resolver_for("edit").action_type == GenerationActionType.EDIT_IMAGE
    assert resolver_for("animate").action_type == GenerationActionType.ANIMATE
    assert resolver_for("publish").action_type == GenerationActionType.PUBLISH
