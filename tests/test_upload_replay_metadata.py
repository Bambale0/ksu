import random

import pytest

from app.api.v1.uploads import _persist_reference_metadata
from app.db.models import User
from app.db.session import SessionFactory
from app.services.media_probe import MediaProbe
from app.services.references import ReferenceService


def _telegram_id() -> int:
    return 971_000_000_000 + random.randint(1, 999_999)


@pytest.mark.asyncio
async def test_upload_replay_refreshes_server_timestamps_before_public_view() -> None:
    """Replay metadata persistence must leave the reference safe to serialize.

    Regression for POST /api/v1/uploads/kie -> 500 (MissingGreenlet):
    ReferenceService.register() commits the replayed row and PostgreSQL updates
    updated_at server-side. The upload endpoint then persists probe metadata,
    commits once more, refreshes the row asynchronously, and only after that
    builds ReferenceService.public_view().
    """
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="ReplayTS")
        session.add(user)
        await session.commit()

        source_url = f"/uploads/refs/video/u/replay-ts/{user.id}.mp4"
        file_hash = "a" * 64

        reference, replayed = await ReferenceService.register(
            session,
            user_id=user.id,
            source_url=source_url,
            kind="video",
            original_filename="clip.mp4",
            content_type="video/mp4",
            file_hash=file_hash,
            source="mini_app_upload",
        )
        assert replayed is False

        # Same URL/hash follows the real upload replay branch and commits an
        # UPDATE, expiring the server-generated updated_at attribute.
        reference, replayed = await ReferenceService.register(
            session,
            user_id=user.id,
            source_url=source_url,
            kind="video",
            original_filename="clip.mp4",
            content_type="video/mp4",
            file_hash=file_hash,
            source="mini_app_upload",
        )
        assert replayed is True

        # This is the endpoint step fixed by the PR: the final commit must be
        # followed by an async refresh before synchronous response serialization.
        await _persist_reference_metadata(
            session,
            reference,
            size_bytes=1234,
            probe=MediaProbe(
                status="ready",
                duration_ms=4000,
                width=720,
                height=1280,
                container="mov,mp4,m4a,3gp,3g2,mj2",
                video_codec="h264",
                audio_codec="aac",
            ),
        )

        view = ReferenceService.public_view(reference)

        assert view["id"] == str(reference.id)
        assert view["kind"] == "video"
        assert view["updated_at"]
        assert view["size_bytes"] == 1234
        assert view["probe_status"] == "ready"
        assert view["duration_ms"] == 4000
        assert view["width"] == 720
        assert view["height"] == 1280
