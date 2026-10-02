from __future__ import annotations

import importlib.util
import json
import stat
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.feed_previews import FeedPreviewService
from app.services.feed_static import FeedStaticStorage, PersistedFeedMedia


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "backfill_feed_faststart",
    ROOT / "scripts" / "backfill_feed_faststart.py",
)
assert SPEC is not None and SPEC.loader is not None
backfill_feed_faststart = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = backfill_feed_faststart
SPEC.loader.exec_module(backfill_feed_faststart)


class _ScalarRows:
    def __init__(self, values: list[uuid.UUID]) -> None:
        self.values = values

    def all(self) -> list[uuid.UUID]:
        return self.values


class _Session:
    def __init__(
        self,
        *,
        generation_ids: list[uuid.UUID] | None = None,
        generation: SimpleNamespace | None = None,
        before_commit=None,
    ) -> None:
        self.generation_ids = generation_ids or []
        self.generation = generation
        self.before_commit = before_commit
        self.commits = 0

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def scalars(self, _statement) -> _ScalarRows:  # type: ignore[no-untyped-def]
        return _ScalarRows(self.generation_ids)

    async def scalar(self, _statement) -> SimpleNamespace | None:  # type: ignore[no-untyped-def]
        return self.generation

    async def commit(self) -> None:
        if self.before_commit is not None:
            self.before_commit()
        self.commits += 1


def _install_sessions(monkeypatch: pytest.MonkeyPatch, sessions: list[_Session]) -> None:
    queued = list(sessions)

    def session_factory() -> _Session:
        assert queued, "unexpected database session"
        return queued.pop(0)

    monkeypatch.setattr(backfill_feed_faststart, "SessionFactory", session_factory)


def _generation(generation_id: uuid.UUID, result_url: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=generation_id,
        status="succeeded",
        publication_scope="feed",
        is_profile_visible=True,
        result_url=result_url,
        parameters={"_result_urls": [result_url]},
    )


@pytest.mark.asyncio
async def test_apply_requires_backup_path_before_opening_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_session() -> _Session:
        raise AssertionError("database must not be opened without a backup path")

    monkeypatch.setattr(backfill_feed_faststart, "SessionFactory", unexpected_session)

    with pytest.raises(ValueError, match="--backup-path is required"):
        await backfill_feed_faststart.backfill(apply=True, backup_path=None, limit=1)


@pytest.mark.asyncio
async def test_dry_run_does_not_convert_or_mutate_feed_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "original.mp4"
    source_bytes = b"\x00\x00\x00\x18ftypisomtest-video"
    source.write_bytes(source_bytes)
    old_url = "/uploads/feed/original.mp4"
    generation = _generation(uuid.uuid4(), old_url)
    query_session = _Session(generation_ids=[generation.id])
    row_session = _Session(generation=generation)
    _install_sessions(monkeypatch, [query_session, row_session])
    monkeypatch.setattr(
        FeedStaticStorage,
        "path_for_url",
        classmethod(lambda _cls, _url: source),
    )
    monkeypatch.setattr(FeedStaticStorage, "mp4_has_faststart", lambda _path: False)

    def unexpected_conversion(*_args: object, **_kwargs: object) -> PersistedFeedMedia:
        raise AssertionError("dry-run must not invoke ffmpeg conversion")

    monkeypatch.setattr(
        FeedStaticStorage,
        "faststart_copy",
        classmethod(unexpected_conversion),
    )

    await backfill_feed_faststart.backfill(apply=False, backup_path=None, limit=1)

    assert generation.result_url == old_url
    assert generation.parameters["_result_urls"] == [old_url]
    assert source.read_bytes() == source_bytes
    assert row_session.commits == 0
    assert "would_update=1" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_apply_fsyncs_backup_before_commit_and_keeps_original_media(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "original.mp4"
    source_bytes = b"\x00\x00\x00\x18ftypisomtest-video"
    source.write_bytes(source_bytes)
    prepared_path = tmp_path / "prepared.mp4"
    prepared_path.write_bytes(b"\x00\x00\x00\x18ftypisomfaststart")
    old_url = "/uploads/feed/original.mp4"
    generation = _generation(uuid.uuid4(), old_url)
    new_url = "/uploads/feed/immutable-faststart.mp4"
    prepared = PersistedFeedMedia(
        public_url=new_url,
        path=prepared_path,
        content_type="video/mp4",
        size_bytes=prepared_path.stat().st_size,
        sha256="test-digest",
        ordinal=0,
    )
    backup_path = tmp_path / "faststart-backup.jsonl"
    query_session = _Session(generation_ids=[generation.id])

    def backup_is_durable() -> None:
        rows = [json.loads(line) for line in backup_path.read_text(encoding="utf-8").splitlines()]
        assert rows == [{"id": str(generation.id), "old_url": old_url, "new_url": new_url}]

    row_session = _Session(generation=generation, before_commit=backup_is_durable)
    _install_sessions(monkeypatch, [query_session, row_session])
    monkeypatch.setattr(
        FeedStaticStorage,
        "path_for_url",
        classmethod(lambda _cls, _url: source),
    )
    monkeypatch.setattr(
        FeedStaticStorage,
        "mp4_has_faststart",
        lambda path: path == prepared_path,
    )
    monkeypatch.setattr(
        FeedStaticStorage,
        "faststart_copy",
        classmethod(lambda _cls, _item, *, generation_id: prepared),
    )
    monkeypatch.setattr(
        FeedPreviewService,
        "preview_url_for",
        classmethod(lambda _cls, _url: "/uploads/feed/poster.jpg"),
    )

    await backfill_feed_faststart.backfill(apply=True, backup_path=backup_path, limit=1)

    assert generation.result_url == new_url
    assert generation.parameters["_result_urls"] == [new_url]
    assert source.read_bytes() == source_bytes
    assert row_session.commits == 1
    assert stat.S_IMODE(backup_path.stat().st_mode) == 0o600


@pytest.mark.asyncio
async def test_restore_only_reverts_generations_still_on_backfilled_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    restored_id = uuid.uuid4()
    changed_id = uuid.uuid4()
    restored = _generation(restored_id, "/uploads/feed/new-1.mp4")
    changed = _generation(changed_id, "/uploads/feed/newer.mp4")
    backup_path = tmp_path / "faststart-backup.jsonl"
    backup_path.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {"id": str(restored_id), "old_url": "/uploads/feed/old-1.mp4", "new_url": "/uploads/feed/new-1.mp4"},
                {"id": str(changed_id), "old_url": "/uploads/feed/old-2.mp4", "new_url": "/uploads/feed/new-2.mp4"},
            )
        )
        + "\n",
        encoding="utf-8",
    )
    restored_session = _Session(generation=restored)
    changed_session = _Session(generation=changed)
    _install_sessions(monkeypatch, [restored_session, changed_session])

    await backfill_feed_faststart.restore(backup_path)

    assert restored.result_url == "/uploads/feed/old-1.mp4"
    assert restored.parameters["_result_urls"] == ["/uploads/feed/old-1.mp4"]
    assert changed.result_url == "/uploads/feed/newer.mp4"
    assert changed.parameters["_result_urls"] == ["/uploads/feed/newer.mp4"]
    assert restored_session.commits == 1
    assert changed_session.commits == 0
    assert "restored=1 skipped=1" in capsys.readouterr().out

@pytest.mark.asyncio
async def test_restore_does_not_overwrite_changed_secondary_media(tmp_path, monkeypatch, capsys):
    generation = _generation(uuid.uuid4(), "/uploads/feed/new-1.mp4")
    generation.parameters["_result_urls"] = [generation.result_url, "/uploads/feed/user-newer.mp4"]
    backup = tmp_path / "multi.jsonl"
    backup.write_text(json.dumps({
        "id": str(generation.id), "old_url": "/uploads/feed/old-1.mp4",
        "new_url": generation.result_url,
        "old_urls": ["/uploads/feed/old-1.mp4", "/uploads/feed/old-2.mp4"],
        "new_urls": [generation.result_url, "/uploads/feed/new-2.mp4"],
    }) + "\n")
    session = _Session(generation=generation)
    _install_sessions(monkeypatch, [session])
    await backfill_feed_faststart.restore(backup)
    assert generation.parameters["_result_urls"][1] == "/uploads/feed/user-newer.mp4"
    assert session.commits == 0
    assert "restored=0 skipped=1" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_backfill_rechecks_public_visibility_after_lock(tmp_path, monkeypatch):
    generation = _generation(uuid.uuid4(), "/uploads/feed/video.mp4")
    generation.publication_scope = "private"
    generation.is_profile_visible = False
    row_session = _Session(generation=generation)
    _install_sessions(monkeypatch, [_Session(generation_ids=[generation.id]), row_session])
    backup = tmp_path / "hidden.jsonl"
    await backfill_feed_faststart.backfill(apply=True, backup_path=backup, limit=1)
    assert row_session.commits == 0
    assert backup.read_text() == ""
    assert generation.result_url == "/uploads/feed/video.mp4"


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1])
async def test_invalid_batch_limit_does_not_open_database_or_backup(tmp_path, monkeypatch, limit):
    def unexpected_session():
        raise AssertionError("database must not open")

    monkeypatch.setattr(backfill_feed_faststart, "SessionFactory", unexpected_session)
    backup = tmp_path / "invalid.jsonl"
    with pytest.raises(ValueError, match="limit must be positive"):
        await backfill_feed_faststart.backfill(apply=True, backup_path=backup, limit=limit)
    assert not backup.exists()
