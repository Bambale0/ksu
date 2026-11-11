"""Customer-facing Kling 4.0 audio contract and supplier-independent presentation.

The product owns the public controls and message copy. Provider capabilities are
an internal routing concern. A generated soundtrack must be requested explicitly
at the native boundary without discarding original-sound intent.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
import uuid

import pytest

from app.api.v1.generations import _generation_view
from app.core.generation_errors import kling4_public_failure_message
from app.db.models import Generation
from app.services.generation_provider_routing import select_kling4_route
from app.services.model_catalog import ModelCatalog
from app.services.model_ui import build_model_ui_schema
from app.services.neironych_video_contracts import (
    NeironychVideoUnsupportedInput, prepare_neironych_kling_input,
)
from app.workers.notifications import _generation_failure_text


REFS = {
    "prompt": "Follow @image_1 and @video_1",
    "duration": 5, "resolution": "720p", "aspect_ratio": "16:9",
    "image_urls": ["https://cdn.example/cup.png"],
    "video_urls": ["https://cdn.example/motion.mp4"],
}


@pytest.mark.parametrize("flag", [None, False])
def test_compatible_native_kling_always_requests_generated_sound(flag):
    request = dict(REFS)
    if flag is not None:
        request["keep_original_sound"] = flag
    output = prepare_neironych_kling_input(request)
    assert output["generate_audio"] is True
    assert output["reference_images"] == [{"url": REFS["image_urls"][0]}]
    assert output["reference_videos"] == [{"url": REFS["video_urls"][0]}]
    assert "keep_original_sound" not in output
    assert request.get("keep_original_sound") is flag


def test_text_only_native_kling_explicitly_generates_sound():
    assert prepare_neironych_kling_input({
        "prompt": "A blue cube", "duration": 3, "resolution": "720p",
    })["generate_audio"] is True


def test_audio_preservation_is_not_silently_translated_to_generated_sound():
    request = {**REFS, "keep_original_sound": True}
    with pytest.raises(NeironychVideoUnsupportedInput):
        prepare_neironych_kling_input(request)
    assert select_kling4_route("kling-4.0", request, ("neironych", "kie")) == (
        ("kie",), "original_sound",
    )
    assert request["keep_original_sound"] is True


def test_public_model_controls_contain_no_internal_supplier_names():
    spec = ModelCatalog.get("kling-4.0")
    schema = build_model_ui_schema({
        "id": spec.id, "known_fields": spec.known_fields,
        "required_fields": spec.required_fields, "price_mode": spec.price_mode,
    })
    labels = {field["name"]: field["label"] for field in schema["fields"]}
    assert labels["keep_original_sound"] == "Сохранить звук исходного видео"
    assert labels["elements"] == "Персонажи и объекты"
    assert labels["voices"] == "Голоса"
    for name in ("keep_original_sound", "elements", "voices"):
        assert not any(term in labels[name].lower() for term in ("kie", "нейроныч", "провайдер"))


@pytest.mark.parametrize("raw", [
    "Kie createTask rejected: 'Credits insufficient'",
    "Neironych contract: Neironych Kling cannot preserve original-sound controls",
    "Kie submission uncertain: timed out",
    "Kie provider_generation_failed",
])
def test_public_kling_errors_never_expose_provider_internals(raw):
    message = kling4_public_failure_message(raw)
    assert message
    assert not any(term in message.lower() for term in (
        "kie", "нейроныч", "provider", "провайдер", "contract", "createTask",
    ))


def test_no_compatible_supplier_error_is_plain_language():
    with pytest.raises(ValueError) as e:
        select_kling4_route("kling-4.0", {**REFS, "keep_original_sound": True}, ("neironych",))
    assert not any(term in str(e.value).lower() for term in ("kie", "нейроныч", "провайдер"))
    assert "звук" in str(e.value).lower() or "настройк" in str(e.value).lower()


def make_generation(model_id="kling-4.0", error="Kie createTask rejected: Credits insufficient"):
    return Generation(
        id=uuid.uuid4(), user_id=uuid.uuid4(), kind="video",
        status="failed", cost_rox=Decimal("25.00"),
        provider="kie", error=error, prompt="A blue cube",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        parameters={"_model_id": model_id, "_model_title": "Kling 4.0", "_media_type": "video"},
    )


def test_generation_api_masks_technical_kling_error_without_disclosing_supplier():
    error = _generation_view(make_generation())["error"]
    assert error == kling4_public_failure_message("Kie createTask rejected: Credits insufficient")
    assert "kie" not in str(error).lower()
    # Do not accidentally hide other models' specific error messages.
    raw = "Kie createTask rejected: Credits insufficient"
    assert _generation_view(make_generation("seedance-2.5", raw))["error"] == raw


def test_telegram_failure_uses_safe_copy_and_one_refund_notice():
    msg = _generation_failure_text(make_generation())
    assert not any(name in msg.lower() for name in ("kie", "нейроныч", "провайдер"))
    assert "ROX" in msg
    assert msg.count("возвращены на баланс") == 1
