from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.services.feed import FeedMediaUnavailableError, FeedService
from app.services.feed_previews import FeedPreviewService
from app.services.feed_static import FeedStaticStorage, FeedStaticStorageError, PersistedFeedMedia
# CLI helpers are not part of the installed application package. Resolve the
# real file, as the existing backfill tests do, so both pytest entrypoints work.
import importlib.util
import sys

_command_path = Path(__file__).resolve().parents[1] / "scripts" / "backfill_feed_faststart.py"
_command_spec = importlib.util.spec_from_file_location("faststart_integration_command", _command_path)
assert _command_spec is not None and _command_spec.loader is not None
command = importlib.util.module_from_spec(_command_spec)
sys.modules[_command_spec.name] = command
_command_spec.loader.exec_module(command)


async def publication(scope: str, urls: list[str], *, order: int = 0) -> uuid.UUID:
    async with SessionFactory() as session:
        user = User(telegram_id=98000000000000 + uuid.uuid4().int % 10000000000, first_name="Merge regression")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id, kind="text_to_video", status="succeeded", prompt="private prompt",
            result_url=urls[0], parameters={"_result_urls": urls, "keep": "unchanged"}, cost_rox=0,
        )
        FeedService.apply_publication_scope(generation, scope)
        generation.feed_published_at = datetime.now(UTC) + timedelta(seconds=order)
        session.add(generation)
        await session.commit()
        return generation.id


def fixture_sessions(monkeypatch: pytest.MonkeyPatch, ids: list[uuid.UUID]) -> None:
    # Limit fixture ownership only. Execute the production SELECT (including its
    # visibility filters and LIMIT) on real PostgreSQL, not a fake all() result.
    @asynccontextmanager
    async def factory():
        async with SessionFactory() as session:
            original_scalars = session.scalars

            async def scalars(statement):
                return await original_scalars(statement.where(Generation.id.in_(ids)))

            session.scalars = scalars
            yield session

    monkeypatch.setattr(command, "SessionFactory", factory)


def fixture_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, urls: list[str]) -> list[str]:
    converted: list[str] = []
    for url in urls:
        (tmp_path / Path(url).name).write_bytes(b"original-video")
    monkeypatch.setattr(FeedStaticStorage, "path_for_url", classmethod(lambda cls, url: tmp_path / Path(url).name))
    monkeypatch.setattr(FeedStaticStorage, "mp4_has_faststart", staticmethod(lambda path: path.name.startswith("ready-")))

    def inspect(path):
        data = path.read_bytes()
        return ".mp4", "video/mp4", len(data), hashlib.sha256(data).hexdigest()

    monkeypatch.setattr(FeedStaticStorage, "_inspect_file", staticmethod(inspect))

    def convert(cls, item, *, generation_id):
        converted.append(item.public_url)
        target = tmp_path / f"ready-{item.path.name}"
        target.write_bytes(b"optimized-video")
        return PersistedFeedMedia(
            public_url=f"/uploads/feed/{target.name}", path=target, content_type="video/mp4",
            size_bytes=target.stat().st_size, sha256="fixture", ordinal=item.ordinal,
        )

    monkeypatch.setattr(FeedStaticStorage, "faststart_copy", classmethod(convert))
    monkeypatch.setattr(FeedPreviewService, "preview_url_for", classmethod(lambda cls, url: "/uploads/feed/poster.jpg"))
    return converted


@pytest.mark.asyncio
async def test_faststart_failure_is_domain_error_and_does_not_publish(monkeypatch, caplog):
    generation_id = await publication("private", ["/uploads/feed/original.mp4"])
    monkeypatch.setattr(FeedStaticStorage, "local_url_exists", classmethod(lambda cls, url: True))

    async def persisted(*args, **kwargs):
        return [SimpleNamespace(public_url="/uploads/feed/original.mp4")]

    def failed(*args, **kwargs):
        raise FeedStaticStorageError("ffmpeg timeout")

    monkeypatch.setattr(FeedStaticStorage, "persist_urls", persisted)
    monkeypatch.setattr(FeedStaticStorage, "faststart_copy", failed)
    async with SessionFactory() as session:
        generation = await session.get(Generation, generation_id)
        before = dict(generation.parameters)
        with pytest.raises(FeedMediaUnavailableError):
            await FeedService.share_to_feed(session, generation_id=generation.id,
                                           owner_user_id=generation.user_id, publication_scope="feed")
        assert f"generation_id={generation.id}" in caplog.text
        assert "private prompt" not in caplog.text
        assert generation.publication_scope == "private"
        assert generation.parameters == before
        assert generation.result_url == "/uploads/feed/original.mp4"
        await session.rollback()


@pytest.mark.asyncio
async def test_backfill_includes_profile_publications_but_not_private(monkeypatch, tmp_path, capsys):
    urls = ["/uploads/feed/profile.mp4", "/uploads/feed/private.mp4"]
    ids = [await publication("profile", [urls[0]]), await publication("private", [urls[1]])]
    fixture_sessions(monkeypatch, ids)
    converted = fixture_storage(monkeypatch, tmp_path, urls)
    await command.backfill(apply=False, backup_path=None, limit=1)
    assert "would_update=1" in capsys.readouterr().out
    assert converted == []


@pytest.mark.asyncio
async def test_multi_video_backfill_and_guarded_restore_preserve_all_media(monkeypatch, tmp_path):
    urls = ["/uploads/feed/first.mp4", "/uploads/feed/second.mp4"]
    generation_id = await publication("feed", urls)
    fixture_sessions(monkeypatch, [generation_id])
    converted = fixture_storage(monkeypatch, tmp_path, urls)
    backup = tmp_path / "backup.jsonl"
    await command.backfill(apply=True, backup_path=backup, limit=1)
    expected = ["/uploads/feed/ready-first.mp4", "/uploads/feed/ready-second.mp4"]
    assert converted == urls
    row = json.loads(backup.read_text())
    assert row["old_urls"] == urls
    assert row["new_urls"] == expected
    async with SessionFactory() as session:
        generation = await session.get(Generation, generation_id)
        assert generation.result_url == expected[0]
        assert generation.parameters == {"_result_urls": expected, "keep": "unchanged"}
    await command.restore(backup)
    async with SessionFactory() as session:
        generation = await session.get(Generation, generation_id)
        assert generation.result_url == urls[0]
        assert generation.parameters == {"_result_urls": urls, "keep": "unchanged"}
    assert all((tmp_path / Path(url).name).read_bytes() == b"original-video" for url in urls)


@pytest.mark.asyncio
async def test_limited_runs_advance_past_already_optimized_rows(monkeypatch, tmp_path):
    urls = ["/uploads/feed/oldest.mp4", "/uploads/feed/newer.mp4"]
    ids = [await publication("feed", [url], order=index) for index, url in enumerate(urls)]
    fixture_sessions(monkeypatch, ids)
    converted = fixture_storage(monkeypatch, tmp_path, urls)
    await command.backfill(apply=True, backup_path=tmp_path / "batch1.jsonl", limit=1)
    assert converted == urls[:1]
    await command.backfill(apply=True, backup_path=tmp_path / "batch2.jsonl", limit=1)
    assert converted == urls
