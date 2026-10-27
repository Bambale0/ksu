from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.local_media_storage import LOCAL_MEDIA_BUCKET
from app.services.trend_workflows import TrendWorkflowService


@pytest.mark.asyncio
async def test_missing_private_photo_bytes_cannot_unlock_a_paid_video(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_LOCAL_ROOT", str(tmp_path))
    owner = uuid4()
    generation = SimpleNamespace(id=uuid4(), user_id=owner, status="succeeded")
    asset = SimpleNamespace(
        id=uuid4(), user_id=owner, generation_id=generation.id, status="ready",
        bucket=LOCAL_MEDIA_BUCKET, object_key="missing.png", content_type="image/png",
    )
    session = AsyncMock()
    session.scalar.side_effect = [SimpleNamespace(generation_id=generation.id), asset]
    session.get.return_value = generation
    with pytest.raises(ValueError, match="unavailable|ready"):
        await TrendWorkflowService._ready_step1_asset(
            session, run=SimpleNamespace(id=uuid4(), user_id=owner), selected_asset_id=asset.id,
        )
