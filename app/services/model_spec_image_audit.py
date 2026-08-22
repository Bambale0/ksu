from __future__ import annotations

from dataclasses import replace

_INSTALLED = False


def install_model_spec_image_audit() -> None:
    """Restore provider-supported image controls hidden by the catalog."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import model_catalog as catalog
    from app.services import model_ui_contract as ui_contract

    gpt2_ids = {"gpt-image-2-t2i", "gpt-image-2-i2i"}
    patched = []
    for spec in catalog.SPECS:
        if spec.id in gpt2_ids and "resolution" not in spec.known_fields:
            fields = list(spec.known_fields)
            fields.append("resolution")
            spec = replace(spec, known_fields=tuple(fields))
        patched.append(spec)
    catalog.SPECS = tuple(patched)
    catalog.ModelCatalog._by_id = {spec.id: spec for spec in catalog.SPECS}

    for model_id in gpt2_ids:
        ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault(model_id, {})[
            "resolution"
        ] = ["1K", "2K", "4K"]
        ui_contract.MODEL_DEFAULTS.setdefault(model_id, {})["resolution"] = "1K"
