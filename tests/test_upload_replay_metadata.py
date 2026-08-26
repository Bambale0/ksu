import random

import pytest

from app.db.models import User
from app.db.session import SessionFactory
from app.services.references import ReferenceService


def _telegram_id() -> int:
    return 971_000_000_000 + random.randint(1, 999_999)


@pytest.mark.asyncio
async def test_public_view_after_reference_update_reads_server_timestamps() -> None:
    """Replay of an uploaded reference must not trigger a sync lazy-refresh.

    Regression for POST /api/v1/uploads/kie -> 500 (MissingGreenlet):
    updated_at is a server-side onupdate column, so after the UPDATE commit
    the ORM expires the attribute even with expire_on_commit=False. Reading
    it afterwards (public_view) attempted a synchronous refresh outside the
    async greenlet.
    """
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="ReplayTS")
        session.add(user)
        await session.commit()

        reference, replayed = await ReferenceService.register(
            session,
            user_id=user.id,
            source_url=f"/uploads/refs/video/u/replay-ts/{user.id}.mp4",
            kind="video",
            original_filename="clip.mp4",
            content_type="video/mp4",
            file_hash=None,
            source="mini_app_upload",
        )
        assert replayed is False

        # Second upload of the same file takes the replay branch: mutate the
        # existing row and commit again, then build the response view.
        reference.size_bytes = 1234
        await session.commit()

        view = ReferenceService.public_view(reference)

        assert view["id"] == str(reference.id)
        assert view["kind"] == "video"
        assert view["updated_at"]
        assert view["size_bytes"] == 1234