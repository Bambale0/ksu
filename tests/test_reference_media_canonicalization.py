from types import SimpleNamespace

from app.services.generation_provider import GenerationProviderService
from app.services.kie_video_contracts import normalize_kie_video_input
from app.services.model_routing import resolve_model_request


def test_nano_banana_2_legacy_photo_refs_become_image_input() -> None:
    result = resolve_model_request(
        "nano-banana-2",
        {
            "prompt": "keep the person from the reference",
            "reference_images": ["https://cdn.example/ref-a.png", "https://cdn.example/ref-b.png"],
        },
    )

    assert result.model_id == "nano-banana-2"
    assert result.mode == "i2i"
    assert result.parameters["image_input"] == [
        "https://cdn.example/ref-a.png",
        "https://cdn.example/ref-b.png",
    ]
    assert "reference_images" not in result.parameters


def test_gpt_image_legacy_photo_ref_switches_to_i2i_contract() -> None:
    result = resolve_model_request(
        "gpt-image-2-t2i",
        {
            "prompt": "edit the reference",
            "reference_image_url": "https://cdn.example/ref.png",
        },
    )

    assert result.model_id == "gpt-image-2-i2i"
    assert result.switched is True
    assert result.parameters["input_urls"] == ["https://cdn.example/ref.png"]
    assert "reference_image_url" not in result.parameters


def test_seedance_legacy_photo_and_video_refs_keep_multimodal_semantics() -> None:
    result = resolve_model_request(
        "seedance-2.0",
        {
            "prompt": "use the character and motion references",
            "reference_images": ["https://cdn.example/character.png"],
            "reference_videos": ["https://cdn.example/motion.mp4"],
            "duration": 8,
        },
    )

    assert result.model_id == "seedance-2.0"
    assert result.mode == "i2v"
    assert result.parameters["reference_image_urls"] == ["https://cdn.example/character.png"]
    assert result.parameters["reference_video_urls"] == ["https://cdn.example/motion.mp4"]
    assert "reference_images" not in result.parameters
    assert "reference_videos" not in result.parameters
    assert "first_frame_url" not in result.parameters

    provider_input = normalize_kie_video_input(result.spec.kie_model, result.parameters)
    assert provider_input["reference_image_urls"] == ["https://cdn.example/character.png"]
    assert provider_input["reference_video_urls"] == ["https://cdn.example/motion.mp4"]


def test_seedance_old_generic_reference_fields_are_moved_to_exact_reference_arrays() -> None:
    result = resolve_model_request(
        "seedance-2.5",
        {
            "prompt": "follow references",
            "image_urls": ["https://cdn.example/look.png"],
            "video_urls": ["https://cdn.example/movement.mp4"],
            "duration": 8,
        },
    )

    assert result.parameters["reference_image_urls"] == ["https://cdn.example/look.png"]
    assert result.parameters["reference_video_urls"] == ["https://cdn.example/movement.mp4"]
    assert "image_urls" not in result.parameters
    assert "video_urls" not in result.parameters
    assert "first_frame_url" not in result.parameters


def test_first_frame_stays_a_frame_and_is_not_duplicated_as_reference() -> None:
    result = resolve_model_request(
        "seedance-2.5",
        {
            "prompt": "animate this frame",
            "first_frame_url": "https://cdn.example/frame.png",
            "duration": 8,
        },
    )

    assert result.parameters["first_frame_url"] == "https://cdn.example/frame.png"
    assert "reference_image_urls" not in result.parameters


def test_provider_input_does_not_shadow_explicit_multimodal_refs_with_legacy_input_url() -> None:
    generation = SimpleNamespace(
        parameters={
            "prompt": "follow the references",
            "reference_image_urls": ["https://cdn.example/look.png"],
            "reference_video_urls": ["https://cdn.example/motion.mp4"],
            "_model_id": "seedance-2.5",
        },
        prompt="follow the references",
        input_url="https://cdn.example/legacy-source.png",
    )

    provider_input = GenerationProviderService._input_for(generation)

    assert provider_input["reference_image_urls"] == ["https://cdn.example/look.png"]
    assert provider_input["reference_video_urls"] == ["https://cdn.example/motion.mp4"]
    assert "image_url" not in provider_input


def test_provider_input_keeps_legacy_input_url_fallback_without_explicit_media() -> None:
    generation = SimpleNamespace(
        parameters={"prompt": "animate source", "_model_id": "legacy-model"},
        prompt="animate source",
        input_url="https://cdn.example/legacy-source.png",
    )

    provider_input = GenerationProviderService._input_for(generation)

    assert provider_input["image_url"] == "https://cdn.example/legacy-source.png"
