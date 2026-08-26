from pathlib import Path

from app.core.config import settings
from app.services.model_catalog import ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema


def _example_upload_limit() -> int:
    for line in Path(".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith("KIE_UPLOAD_MAX_BYTES="):
            return int(line.split("=", 1)[1])
    raise AssertionError("KIE_UPLOAD_MAX_BYTES is missing from .env.example")


def test_global_kie_upload_limit_covers_largest_public_model_reference() -> None:
    largest_public_bytes = 0
    largest_fields: list[str] = []

    for model in ModelCatalog.list():
        schema = build_public_model_ui_schema(model)
        for field in schema.get("fields", []):
            max_size_mb = field.get("max_size_mb")
            if max_size_mb is None:
                continue
            size_bytes = int(max_size_mb) * 1024 * 1024
            if size_bytes > largest_public_bytes:
                largest_public_bytes = size_bytes
                largest_fields = [f"{model['id']}.{field['name']}"]
            elif size_bytes == largest_public_bytes:
                largest_fields.append(f"{model['id']}.{field['name']}")

    assert largest_public_bytes == 200 * 1024 * 1024
    assert "seedance-2.0.reference_video_urls" in largest_fields
    assert settings.kie_upload_max_bytes >= largest_public_bytes
    assert _example_upload_limit() >= largest_public_bytes
