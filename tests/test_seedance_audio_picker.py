import pytest

from app.services.model_ui_contract import build_public_model_ui_schema


@pytest.mark.parametrize("model_id", ["seedance-2.0", "seedance-2.0-fast", "seedance-2.0-mini", "seedance-2.5"])
def test_seedance_audio_picker_matches_verified_audio_formats(model_id):
    schema = build_public_model_ui_schema({
        "id": model_id,
        "known_fields": ["reference_image_urls", "reference_video_urls", "reference_audio_urls"],
    })
    fields = {field["name"]: field for field in schema["fields"]}
    accepted = set(fields["reference_audio_urls"]["accept"].split(","))
    assert {".mp3", ".wav", "audio/mpeg", "audio/wav"} <= accepted
    assert "audio/*" not in accepted
    assert not any(value.startswith("video/") for value in accepted)
    assert fields["reference_video_urls"]["accept"] == "video/*"
    assert fields["reference_image_urls"]["accept"] == "image/*"
