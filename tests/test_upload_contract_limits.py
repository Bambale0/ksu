from app.core.config import settings
from app.services.model_catalog import ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema


def test_global_kie_upload_limit_covers_largest_public_model_reference() -> None:
    largest_public_bytes = 0
    largest_field = ""

    for model in ModelCatalog.list():
        schema = build_public_model_ui_schema(model)
        for field in schema.get("fields", []):
            max_size_mb = field.get("max_size_mb")
            if max_size_mb is None:
                continue
            size_bytes = int(max_size_mb) * 1024 * 1024
            if size_bytes > largest_public_bytes:
                largest_public_bytes = size_bytes
                largest_field = f"{model['id']}.{field['name']}"

    assert largest_public_bytes == 200 * 1024 * 1024
    assert largest_field == "seedance-2.5.reference_video_urls"
    assert settings.kie_upload_max_bytes >= largest_public_bytes
