"""Owned-media completion must not hide incomplete provider outputs."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import uuid

from app.api.v1.generations import _generation_view


def generation():
    now = datetime.now(timezone.utc)
    urls = ["https://provider.invalid/one.png", "https://provider.invalid/two.png"]
    return SimpleNamespace(
        id=uuid.uuid4(), kind="generate_or_edit", status="succeeded",
        prompt="", action_type="trend", cost_rox=Decimal("25"),
        parameters={"_model_id": "nano-banana-pro", "_result_urls": urls},
        result_url=urls[0], error=None, created_at=now, updated_at=now,
    )


def owned(path):
    return {"id": str(uuid.uuid4()), "url": path}


def test_multi_media_needs_all_owned_assets():
    source = generation()
    partial = _generation_view(source, owned_media=[owned("/one")],
                               media_progress={"ready": 1, "pending": 1})
    assert partial["media_delivery"] == {"expected": 2, "ready": 1, "failed": 0, "state": "pending"}
    full = _generation_view(source, owned_media=[owned("/one"), owned("/two")],
                            media_progress={"ready": 2})
    assert full["media_delivery"]["state"] == "ready"


def test_failed_media_ingest_is_reported_explicitly():
    source = generation()
    partial = _generation_view(source, owned_media=[owned("/one")],
                               media_progress={"ready": 1, "failed": 1})
    assert partial["status"] == "succeeded"
    assert partial["media_delivery"] == {"expected": 2, "ready": 1, "failed": 1, "state": "failed"}

def test_one_failed_ordinal_does_not_stop_remaining_media_ingestion():
    source = generation()
    partial = _generation_view(source, owned_media=[],
                               media_progress={"failed": 1, "pending": 1})
    assert partial["media_delivery"] == {
        "expected": 2, "ready": 0, "failed": 1, "state": "pending"
    }
