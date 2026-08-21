from pathlib import Path

from app.services.model_catalog import ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema


def test_every_model_field_has_a_dynamic_control() -> None:
    models = ModelCatalog.list()
    assert models
    for model in models:
        schema = build_public_model_ui_schema(model)
        controls = {field["name"]: field for field in schema["fields"]}
        assert set(model["known_fields"]) == set(controls), model["id"]
        for field in controls.values():
            assert field["label"]
            assert field["control"] in {
                "text",
                "textarea",
                "number",
                "toggle",
                "combobox",
                "file",
                "files",
                "json",
            }
            assert field["group"] in {"prompt", "references", "output", "advanced"}


def test_scenarios_only_reference_fields_from_the_same_model() -> None:
    for model in ModelCatalog.list():
        schema = build_public_model_ui_schema(model)
        known = set(model["known_fields"])
        for scenario in schema.get("scenario", {}).get("items", []):
            assert set(scenario.get("visible_fields", [])) <= known, model["id"]
            assert set(scenario.get("clear_fields", [])) <= known, model["id"]
            assert set(scenario.get("required_fields", [])) <= known, model["id"]
            assert set(scenario.get("required_any", [])) <= known, model["id"]


def test_mode_specific_inputs_are_required_by_the_contract() -> None:
    models = {model["id"]: model for model in ModelCatalog.list()}

    seedance = build_public_model_ui_schema(models["seedance-2.0"])
    seedance_modes = {item["id"]: item for item in seedance["scenario"]["items"]}
    seedance_fields = {field["name"]: field for field in seedance["fields"]}
    assert seedance_modes["first_frame"]["title"] == "Референс"
    assert seedance_fields["first_frame_url"]["label"] == "Референс"
    assert seedance_modes["first_frame"]["required_fields"] == ["first_frame_url"]
    assert seedance_modes["first_last"]["required_fields"] == [
        "first_frame_url",
        "last_frame_url",
    ]
    assert seedance_modes["references"]["required_any"] == [
        "reference_image_urls",
        "reference_video_urls",
        "reference_audio_urls",
    ]


def test_video_duration_fields_use_model_specific_kie_options() -> None:
    models = {model["id"]: model for model in ModelCatalog.list()}
    expected_options = {
        "wan-2.7-t2v": [5],
        "wan-2.7-i2v": [5],
        "wan-2.7-video-edit": [0],
        "wan-2.7-r2v": [5],
        "seedance-1.5-pro": [8],
        "seedance-2.0": [5, 10, 15],
        "seedance-2.0-fast": [5, 10, 15],
        "seedance-2.0-mini": [5, 10, 15],
        "seedance-2.5": [5, 10, 15],
        "kling-3.0": list(range(3, 16)),
        "gemini-omni-video": [4],
        "grok-video-t2v": [6],
        "grok-video-i2v": [6],
        "grok-video-1.5": [8],
    }

    for model_id, options in expected_options.items():
        model = models.get(model_id)
        if not model:
            continue
        schema = build_public_model_ui_schema(model)
        fields = {field["name"]: field for field in schema["fields"]}
        duration = fields["duration"]
        assert duration["control"] == "combobox", model_id
        assert duration["suggestions"] == options, model_id
        assert duration["suffix"] == "с", model_id

    checked = 0
    for model in models.values():
        if model["media_type"] != "video" or "duration" not in model["known_fields"]:
            continue
        schema = build_public_model_ui_schema(model)
        duration = {field["name"]: field for field in schema["fields"]}["duration"]
        assert duration["control"] == "combobox", model["id"]
        assert duration.get("suggestions"), model["id"]
        checked += 1
    assert checked >= 1


def test_every_per_second_model_can_supply_billing_seconds() -> None:
    for model in ModelCatalog.list():
        if model["price_mode"] != "per_second":
            continue
        schema = build_public_model_ui_schema(model)
        has_duration = "duration" in model["known_fields"]
        has_explicit_billing = bool(schema.get("billing_seconds"))
        assert has_duration or has_explicit_billing, model["id"]


def test_kling_motion_upload_limits_match_provider_contract() -> None:
    models = {model["id"]: model for model in ModelCatalog.list()}
    schema = build_public_model_ui_schema(models["kling-motion-3.0"])
    fields = {field["name"]: field for field in schema["fields"]}
    assert fields["input_urls"]["max_items"] == 1
    assert fields["input_urls"]["max_size_mb"] == 10
    assert fields["video_urls"]["max_items"] == 1
    assert fields["video_urls"]["max_size_mb"] == 100


def test_next_mini_app_source_is_packaged_for_static_export() -> None:
    root = Path(__file__).resolve().parents[1]
    frontend = root / "frontend" / "mini-app"
    for relative in (
        "package.json",
        "next.config.mjs",
        "app/page.tsx",
        "app/globals.css",
        "components/roxy-app.tsx",
        "lib/api.ts",
    ):
        path = frontend / relative
        assert path.exists(), relative
        assert path.stat().st_size > 100, relative

    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "RUN npm run build" in dockerfile
    assert "rm -rf ./app/web/mini_app" in dockerfile
    assert "COPY --from=miniapp /src/frontend/mini-app/out ./app/web/mini_app" in dockerfile
