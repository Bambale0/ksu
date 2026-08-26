from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.api.v1.uploads import _persist_reference_metadata
from app.services.media_probe import MediaProbe
from app.services.references import ReferenceService


class RecordingSession:
    def __init__(self) -> None:
        self.committed = False
        self.refreshed: object | None = None

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, value: object) -> None:
        self.refreshed = value


class ReferenceStub:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.id = uuid4()
        self.kind = "image"
        self.label = None
        self.source_url = "/uploads/refs/image/user/2026/08/reference.png"
        self.original_filename = "reference.png"
        self.content_type = "image/png"
        self.size_bytes = None
        self.probe_status = None
        self.duration_ms = None
        self.width = None
        self.height = None
        self.container = None
        self.video_codec = None
        self.audio_codec = None
        self.source = "mini_app_upload"
        self.created_at = now
        self.updated_at = now
        self.last_used_at = now


@pytest.mark.asyncio
async def test_upload_metadata_refreshes_reference_before_public_response() -> None:
    session = RecordingSession()
    reference = ReferenceStub()

    await _persist_reference_metadata(
        session,  # type: ignore[arg-type]
        reference,
        size_bytes=123,
        probe=MediaProbe(status="ready", width=640, height=480),
    )

    view = ReferenceService.public_view(reference)  # type: ignore[arg-type]

    assert session.committed is True
    assert session.refreshed is reference
    assert view["updated_at"]
    assert view["size_bytes"] == 123
    assert view["width"] == 640
    assert view["height"] == 480
