from pathlib import Path

from app.services.model_catalog import ModelCatalog
from app.services.model_ui import build_model_ui_schema


def test_every_model_field_has_a_dynamic_control() -> None:
    models = ModelCatalog.list()
    assert models
    for model in models:
        schema = build_model_ui_schema(model)
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
        schema = build_model_ui_schema(model)
        known = set(model["known_fields"])
        for scenario in schema.get("scenario", {}).get("items", []):
            assert set(scenario.get("visible_fields", [])) <= known, model["id"]
            assert set(scenario.get("clear_fields", [])) <= known, model["id"]


def test_every_per_second_model_can_supply_billing_seconds() -> None:
    for model in ModelCatalog.list():
        if model["price_mode"] != "per_second":
            continue
        schema = build_model_ui_schema(model)
        has_duration = "duration" in model["known_fields"]
        has_explicit_billing = bool(schema.get("billing_seconds"))
        assert has_duration or has_explicit_billing, model["id"]


def test_mini_app_assets_are_packaged() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "web" / "mini_app"
    for name in ("index.html", "styles.css", "app.js"):
        path = root / name
        assert path.exists(), name
        assert path.stat().st_size > 100, name
