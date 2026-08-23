from app.services.model_routing import resolve_model_request
from app.services.model_ui_contract import build_public_model_ui_schema
from app.services.model_catalog import ModelCatalog


def test_reference_capable_image_product_routes_to_text_without_ref() -> None:
    routed = resolve_model_request(
        "gpt-image-2-i2i",
        {"prompt": "portrait"},
    )

    assert routed.model_id == "gpt-image-2-t2i"
    assert routed.mode == "t2i"
    assert routed.switched is True


def test_reference_capable_image_product_routes_to_i2i_with_ref() -> None:
    routed = resolve_model_request(
        "gpt-image-2-i2i",
        {"prompt": "portrait", "input_urls": ["https://example.com/ref.png"]},
    )

    assert routed.model_id == "gpt-image-2-i2i"
    assert routed.mode == "i2i"
    assert routed.parameters["input_urls"] == ["https://example.com/ref.png"]


def test_roxy_owned_uploaded_photo_routes_to_i2i() -> None:
    routed = resolve_model_request(
        "gpt-image-2-i2i",
        {"prompt": "portrait", "input_urls": ["/uploads/refs/image/u/2026/08/ref.png"]},
    )

    assert routed.model_id == "gpt-image-2-i2i"
    assert routed.mode == "i2i"
    assert routed.parameters["input_urls"] == ["/uploads/refs/image/u/2026/08/ref.png"]


def test_video_reference_routes_to_i2v() -> None:
    routed = resolve_model_request(
        "wan-2.7-i2v",
        {
            "prompt": "follow motion",
            "reference_video_urls": ["/uploads/refs/video/u/2026/08/motion.mp4"],
        },
    )

    assert routed.model_id == "wan-2.7-i2v"
    assert routed.mode == "i2v"
    assert routed.parameters["first_clip_url"] == "/uploads/refs/video/u/2026/08/motion.mp4"


def test_input_url_is_promoted_to_target_reference_field() -> None:
    routed = resolve_model_request(
        "seedream-4.5-edit",
        {"prompt": "keep face, change clothes"},
        input_url="https://example.com/ref.png",
    )

    assert routed.model_id == "seedream-4.5-edit"
    assert routed.parameters["image_urls"] == ["https://example.com/ref.png"]


def test_reference_fields_are_optional_in_public_auto_ui_schema() -> None:
    model = ModelCatalog.get("gpt-image-2-i2i").public_dict()
    schema = build_public_model_ui_schema(model)
    fields = {field["name"]: field for field in schema["fields"]}

    assert schema["auto_mode"]["enabled"] is True
    assert fields["input_urls"]["required"] is False
