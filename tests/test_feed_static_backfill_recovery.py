import importlib.util
import socket
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "backfill_feed_static",
    ROOT / "scripts" / "backfill_feed_static.py",
)
assert SPEC is not None and SPEC.loader is not None
backfill_feed_static = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = backfill_feed_static
SPEC.loader.exec_module(backfill_feed_static)


class _Session:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _generation(**parameters: object) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        parameters=parameters,
        result_url="/uploads/feed/missing.jpg",
    )


@pytest.mark.asyncio
async def test_feed_backfill_recovers_original_media_asset_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _generation(_result_urls=["/uploads/feed/missing.jpg"])
    session = _Session()
    source_url = "https://provider.example/original.jpg"
    calls: list[list[str]] = []

    monkeypatch.setattr(
        backfill_feed_static.FeedStaticStorage,
        "local_url_exists",
        lambda value: False,
    )

    async def asset_sources(*args: object, **kwargs: object) -> list[str]:
        return [source_url]

    async def s3_sources(*args: object, **kwargs: object) -> list[str]:
        raise AssertionError("asset source should be tried before object-storage fallback")

    async def persist_urls(urls: list[str], *, generation_id: uuid.UUID) -> list[SimpleNamespace]:
        assert generation_id == generation.id
        calls.append(urls)
        return [SimpleNamespace(public_url="/uploads/feed/recovered.jpg")]

    monkeypatch.setattr(backfill_feed_static, "_asset_source_urls", asset_sources)
    monkeypatch.setattr(backfill_feed_static, "_s3_urls", s3_sources)
    monkeypatch.setattr(backfill_feed_static.FeedStaticStorage, "persist_urls", persist_urls)
    monkeypatch.setattr(backfill_feed_static, "_ensure_previews", lambda urls: None)

    changed = await backfill_feed_static._persist_generation(session, generation)

    assert changed is True
    assert calls == [[source_url]]
    assert generation.result_url == "/uploads/feed/recovered.jpg"
    assert generation.parameters["_provider_result_urls"] == [source_url]
    assert generation.parameters["_result_urls"] == ["/uploads/feed/recovered.jpg"]
    assert generation.parameters["_feed_static"] is True
    assert session.commits == 1


@pytest.mark.asyncio
async def test_feed_backfill_falls_through_dns_failure_to_fresh_object_storage_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_url = "https://provider.example/expired.jpg"
    s3_url = "https://storage.example/fresh.jpg"
    generation = _generation(
        _provider_result_urls=[provider_url],
        _result_urls=["/uploads/feed/missing.jpg"],
    )
    session = _Session()
    calls: list[list[str]] = []

    monkeypatch.setattr(
        backfill_feed_static.FeedStaticStorage,
        "local_url_exists",
        lambda value: False,
    )

    async def asset_sources(*args: object, **kwargs: object) -> list[str]:
        return []

    async def s3_sources(*args: object, **kwargs: object) -> list[str]:
        return [s3_url]

    async def persist_urls(urls: list[str], *, generation_id: uuid.UUID) -> list[SimpleNamespace]:
        assert generation_id == generation.id
        calls.append(urls)
        if urls == [provider_url]:
            raise socket.gaierror(socket.EAI_AGAIN, "temporary name resolution failure")
        return [SimpleNamespace(public_url="/uploads/feed/recovered-from-s3.jpg")]

    monkeypatch.setattr(backfill_feed_static, "_asset_source_urls", asset_sources)
    monkeypatch.setattr(backfill_feed_static, "_s3_urls", s3_sources)
    monkeypatch.setattr(backfill_feed_static.FeedStaticStorage, "persist_urls", persist_urls)
    monkeypatch.setattr(backfill_feed_static, "_ensure_previews", lambda urls: None)

    changed = await backfill_feed_static._persist_generation(session, generation)

    assert changed is True
    assert calls == [[provider_url], [s3_url]]
    assert generation.result_url == "/uploads/feed/recovered-from-s3.jpg"
    assert generation.parameters["_provider_result_urls"] == [provider_url]
    assert session.commits == 1
