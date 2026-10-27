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


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [None, {"ContentLength": 0}, {"ContentLength": 123, "DeleteMarker": True}])
async def test_configured_remote_storage_is_not_proof_of_readable_photo(monkeypatch, response) -> None:
    from botocore.exceptions import ClientError
    from app.services.object_storage import ObjectStorage

    owner = uuid4()
    generation = SimpleNamespace(id=uuid4(), user_id=owner, status="succeeded")
    asset = SimpleNamespace(
        id=uuid4(), user_id=owner, generation_id=generation.id, status="ready",
        bucket="synthetic-legacy-bucket", object_key="private/photo.png", content_type="image/png",
    )
    probe = AsyncMock(return_value=response)
    if response is None:
        probe.side_effect = ClientError({"Error": {"Code": "404", "Message": "Missing synthetic object"}}, "HeadObject")
    monkeypatch.setattr(ObjectStorage, "configured", staticmethod(lambda: True))
    monkeypatch.setattr(ObjectStorage, "head_object", probe, raising=False)
    session = AsyncMock()
    session.scalar.side_effect = [SimpleNamespace(generation_id=generation.id), asset]
    session.get.return_value = generation
    with pytest.raises(ValueError, match="unavailable"):
        await TrendWorkflowService._ready_step1_asset(
            session, run=SimpleNamespace(id=uuid4(), user_id=owner), selected_asset_id=asset.id,
        )
    probe.assert_awaited_once_with(key=asset.object_key, bucket=asset.bucket)


@pytest.mark.asyncio
async def test_readable_remote_photo_is_verified_without_publishing(monkeypatch) -> None:
    from app.services.object_storage import ObjectStorage

    owner = uuid4()
    generation = SimpleNamespace(id=uuid4(), user_id=owner, status="succeeded")
    asset = SimpleNamespace(
        id=uuid4(), user_id=owner, generation_id=generation.id, status="ready",
        bucket="synthetic-legacy-bucket", object_key="private/photo.png", content_type="image/png",
    )
    probe = AsyncMock(return_value={"ContentLength": 123, "ContentType": "image/png"})
    monkeypatch.setattr(ObjectStorage, "configured", staticmethod(lambda: True))
    monkeypatch.setattr(ObjectStorage, "head_object", probe, raising=False)
    session = AsyncMock()
    session.scalar.side_effect = [SimpleNamespace(generation_id=generation.id), asset]
    session.get.return_value = generation
    result = await TrendWorkflowService._ready_step1_asset(
        session, run=SimpleNamespace(id=uuid4(), user_id=owner), selected_asset_id=asset.id,
    )
    assert result is asset
    probe.assert_awaited_once_with(key=asset.object_key, bucket=asset.bucket)


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [True, False])
async def test_legacy_metadata_probe_runs_off_loop_and_closes_client(monkeypatch, failed) -> None:
    import threading
    from botocore.exceptions import ClientError
    from app.services.object_storage import ObjectStorage

    loop_thread = threading.get_ident()
    calls = []

    class Client:
        def head_object(self, **kwargs):
            calls.append(("head", threading.get_ident(), kwargs))
            if failed:
                raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
            return {"ContentLength": 123}

        def close(self):
            calls.append(("close", threading.get_ident()))

    def client(*, metadata_probe=False):
        assert metadata_probe is True
        assert threading.get_ident() != loop_thread
        return Client()

    monkeypatch.setattr(ObjectStorage, "configured", staticmethod(lambda: True))
    monkeypatch.setattr(ObjectStorage, "_build_client", staticmethod(client))
    if failed:
        with pytest.raises(ClientError):
            await ObjectStorage.head_object(key="private/photo.png", bucket="synthetic-bucket")
    else:
        assert await ObjectStorage.head_object(key="private/photo.png", bucket="synthetic-bucket") == {"ContentLength": 123}
    assert [item[0] for item in calls] == ["head", "close"]
    assert calls[0][1] != loop_thread
    assert calls[0][2] == {"Bucket": "synthetic-bucket", "Key": "private/photo.png"}


def test_legacy_metadata_probe_has_configured_bounded_timeouts(monkeypatch) -> None:
    from app.core.config import settings
    from app.services import object_storage

    captured = {}
    monkeypatch.setattr(settings, "media_ingest_connect_timeout_seconds", 2.5)

    def client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(object_storage.boto3, "client", client)
    object_storage.ObjectStorage._build_client(metadata_probe=True)
    config = captured["config"]
    assert config.connect_timeout == 2.5
    assert config.read_timeout == 2.5
    assert config.retries["total_max_attempts"] == 1
