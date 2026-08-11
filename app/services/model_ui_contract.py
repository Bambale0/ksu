from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.model_ui import build_model_ui_schema

SEEDANCE_MODELS = {
    "seedance-2.0",
    "seedance-2.0-fast",
    "seedance-2.0-mini",
    "seedance-2.5",
}


def build_public_model_ui_schema(model: dict[str, Any]) -> dict[str, Any]:
    schema = deepcopy(build_model_ui_schema(model))
    model_id = str(model["id"])

    scenario = schema.get("scenario")
    if isinstance(scenario, dict):
        for item in scenario.get("items", []):
            visible = list(item.get("visible_fields", []))
            scenario_id = str(item.get("id") or "")
            if model_id in SEEDANCE_MODELS:
                if scenario_id == "references":
                    item["required_any"] = visible
                elif scenario_id != "text":
                    item["required_fields"] = visible
            elif model_id == "wan-2.7-i2v":
                item["required_fields"] = visible

    if model_id in {"kling-motion-2.6", "kling-motion-3.0"}:
        for field in schema.get("fields", []):
            if field.get("name") == "input_urls":
                field["max_size_mb"] = 10
                field["max_items"] = 1
            elif field.get("name") == "video_urls":
                field["max_size_mb"] = 100
                field["max_items"] = 1

    return schema
