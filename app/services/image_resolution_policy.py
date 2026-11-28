from __future__ import annotations

from app.services.model_catalog import ModelCatalog
from app.services.model_ui_contract import MODEL_FIELD_SUGGESTIONS


def image_resolution_options(model_id: str) -> list[str]:
    """Only native K-resolution choices advertised by the current image model."""
    spec = ModelCatalog.get(model_id)
    if spec.media_type != "image" or "resolution" not in spec.known_fields:
        return []
    suggestions = MODEL_FIELD_SUGGESTIONS.get(model_id, {}).get("resolution", [])
    return list(dict.fromkeys(value for value in suggestions if value in ("1K", "2K", "4K")))
