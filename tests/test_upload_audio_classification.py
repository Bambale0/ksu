from __future__ import annotations

import io
import shutil
import subprocess
import uuid

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from app.api.deps import get_current_user, get_redis
from app.api.v1.reference_presets import router as references_router
from app.api.v1.uploads import router as uploads_router
from app.core.config import settings
from app.db.models import User
from app.db.session import SessionFactory
from app.services.media_probe import probe_media_stream


class UploadRedis:
    async def eval(self, *_args: object) -> list[int]:
        return [1, 60]


@pytest.fixture
def audio_mp4(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe required for real media classification")
    path = tmp_path / "sound.mp4"
    subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=1", "-c:a", "aac", str(path)],
        check=True, capture_output=True, timeout=20,
    )
    return path.read_bytes()


@pytest.fixture
def covered_audio_mp4(tmp_path, audio_mp4):
    source = tmp_path / "source.m4a"
    source.write_bytes(audio_mp4)
    cover = tmp_path / "cover.png"
    Image.new("RGB", (16, 16), "blue").save(cover)
    target = tmp_path / "with-cover.m4a"
    subprocess.run(
        [shutil.which("ffmpeg"), "-nostdin", "-v", "error", "-i", str(source),
         "-i", str(cover), "-map", "0:a", "-map", "1:v", "-c", "copy",
         "-disposition:v", "attached_pic", str(target)],
        check=True, capture_output=True, timeout=20,
    )
    return target.read_bytes()


def test_audio_cover_art_is_not_a_video_stream(covered_audio_mp4) -> None:
    result = probe_media_stream(io.BytesIO(covered_audio_mp4), "sound.m4a")
    assert result.status == "ready"
    assert result.audio_codec == "aac"
    assert result.has_video is False
    assert result.video_codec is None
    assert result.width is None
    assert result.height is None


@pytest.fixture
async def upload_client(tmp_path, monkeypatch):
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "references"))
    app = FastAPI()
    app.include_router(uploads_router, prefix="/api/v1")
    app.include_router(references_router, prefix="/api/v1")
    async with SessionFactory() as session:
        owner = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Audio upload QA")
        other = User(telegram_id=uuid.uuid4().int % 10**14, first_name="Other QA")
        session.add_all([owner, other])
        await session.commit()
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_redis] = UploadRedis
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        yield client, app, other


@pytest.mark.asyncio
@pytest.mark.parametrize("media_fixture", ["audio_mp4", "covered_audio_mp4"])
async def test_audio_only_mp4_upload_is_saved_and_replayed_as_audio(
    media_fixture, request, upload_client,
) -> None:
    audio_mp4 = request.getfixturevalue(media_fixture)
    client, app, other = upload_client
    response = await client.post(
        "/api/v1/uploads/kie", files={"file": ("sound.mp4", audio_mp4, "video/mp4")},
    )
    assert response.status_code == 201, response.text
    first = response.json()
    assert first["reference"]["kind"] == "audio"
    assert first["mime_type"] == "audio/mp4"
    assert "/audio/" in first["url"]
    assert first["url"].endswith(".m4a")
    assert first["probe_status"] == "ready"
    assert first["duration_ms"] > 0
    assert first["video_codec"] is None
    assert first["audio_codec"] == "aac"

    response = await client.post(
        "/api/v1/uploads/kie", files={"file": ("again.mp4", audio_mp4, "video/mp4")},
    )
    assert response.status_code == 201
    repeated = response.json()
    assert repeated["replayed"] is True
    assert repeated["reference"]["id"] == first["reference"]["id"]
    assert repeated["url"] == first["url"]
    audio = (await client.get("/api/v1/references?kind=audio")).json()["items"]
    assert [item["id"] for item in audio] == [first["reference"]["id"]]
    assert (await client.get("/api/v1/references?kind=video")).json()["items"] == []

    app.dependency_overrides[get_current_user] = lambda: other
    assert (await client.get("/api/v1/references")).json()["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("extension", "codec", "declared", "expected"), [
    ("mp3", "libmp3lame", "video/mp4", "audio/mpeg"),
    ("ogg", "libvorbis", "video/ogg", "audio/ogg"),
    ("wav", "pcm_s16le", "video/mp4", "audio/wav"),
    ("aac", "aac", "video/mp4", "audio/aac"),
    ("flac", "flac", "video/mp4", "audio/flac"),
    ("aiff", "pcm_s16be", "video/mp4", "audio/aiff"),
    ("m4a", "aac", "application/octet-stream", "audio/mp4"),
    ("m4a", "aac", "audio/mp4", "audio/mp4"),
])
async def test_verified_audio_container_decides_saved_kind(
    extension, codec, declared, expected, audio_mp4, tmp_path, upload_client,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(audio_mp4)
    target = tmp_path / f"sound.{extension}"
    subprocess.run(
        [shutil.which("ffmpeg"), "-nostdin", "-v", "error", "-i", str(source),
         "-c:a", codec, str(target)],
        check=True, capture_output=True, timeout=20,
    )
    client, _, _ = upload_client
    response = await client.post(
        "/api/v1/uploads/kie", files={"file": (target.name, target.read_bytes(), declared)},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["reference"]["kind"] == "audio"
    assert payload["mime_type"] == expected
    assert payload["probe_status"] == "ready"
    assert "/audio/" in payload["url"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("extension", "codec", "declared"), [
    ("mkv", "aac", "video/x-matroska"),
    ("webm", "libopus", "video/webm"),
    ("mov", "pcm_s16le", "video/quicktime"),
])
async def test_ambiguous_demuxer_alias_does_not_relabel_container(
    extension, codec, declared, audio_mp4, tmp_path, upload_client,
):
    source = tmp_path / "source.mp4"
    source.write_bytes(audio_mp4)
    target = tmp_path / f"sound.{extension}"
    subprocess.run(
        [shutil.which("ffmpeg"), "-nostdin", "-v", "error", "-i", str(source),
         "-c:a", codec, str(target)],
        check=True, capture_output=True, timeout=20,
    )
    client, _, _ = upload_client
    response = await client.post(
        "/api/v1/uploads/kie", files={"file": (target.name, target.read_bytes(), declared)},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["mime_type"] == declared
    assert payload["reference"]["kind"] == "video"


@pytest.mark.asyncio
@pytest.mark.parametrize("with_audio", [True, False])
async def test_real_video_upload_remains_video(with_audio, audio_mp4, tmp_path, upload_client):
    target = tmp_path / "movie.mp4"
    inputs = ["-f", "lavfi", "-i", "color=blue:size=16x16:rate=10:duration=1"]
    if with_audio:
        source = tmp_path / "source.mp4"
        source.write_bytes(audio_mp4)
        inputs += ["-i", str(source), "-c:a", "copy"]
    subprocess.run(
        [shutil.which("ffmpeg"), "-nostdin", "-v", "error", *inputs,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target)],
        check=True, capture_output=True, timeout=20,
    )
    client, _, _ = upload_client
    response = await client.post(
        "/api/v1/uploads/kie", files={"file": (target.name, target.read_bytes(), "video/mp4")},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["reference"]["kind"] == "video"
    assert payload["mime_type"] == "video/mp4"
    assert payload["video_codec"] == "h264"


@pytest.mark.asyncio
async def test_failed_probe_keeps_existing_unverified_upload_behavior(upload_client):
    client, _, _ = upload_client
    response = await client.post(
        "/api/v1/uploads/kie", files={"file": ("broken.mp4", b"broken", "video/mp4")},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["reference"]["kind"] == "video"
    assert payload["mime_type"] == "video/mp4"
    assert payload["probe_status"] == "failed"


@pytest.mark.asyncio
async def test_missing_probe_keeps_existing_unverified_upload_behavior(
    audio_mp4, upload_client, monkeypatch,
):
    monkeypatch.setattr("app.services.media_probe.shutil.which", lambda _name: None)
    client, _, _ = upload_client
    response = await client.post(
        "/api/v1/uploads/kie", files={"file": ("sound.mp4", audio_mp4, "video/mp4")},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["reference"]["kind"] == "video"
    assert payload["probe_status"] == "unavailable"


@pytest.mark.asyncio
async def test_audio_bytes_cannot_bypass_unsupported_mime_or_auth(audio_mp4, upload_client, monkeypatch):
    client, app, _ = upload_client
    response = await client.post(
        "/api/v1/uploads/kie", files={"file": ("sound.svg", audio_mp4, "image/svg+xml")},
    )
    assert response.status_code == 415
    assert (await client.get("/api/v1/references")).json()["items"] == []
    monkeypatch.setattr(settings, "bot_token", "123456:test-only")
    del app.dependency_overrides[get_current_user]
    response = await client.post(
        "/api/v1/uploads/kie", files={"file": ("sound.mp4", audio_mp4, "video/mp4")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize('media_fixture', ['audio_mp4', 'covered_audio_mp4'])
async def test_template_endpoint_uses_probed_audio_container(media_fixture, request, upload_client):
    from app.db.models import AdminAccount

    audio_bytes = request.getfixturevalue(media_fixture)
    client, app, _other = upload_client
    owner = app.dependency_overrides[get_current_user]()
    async with SessionFactory() as session:
        session.add(AdminAccount(user_id=owner.id, role='admin'))
        await session.commit()
    response = await client.post('/api/v1/uploads/template-audio', files={'file': ('sound.mp4', audio_bytes, 'video/mp4')})
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload['reference']['kind'] == 'audio'
    assert payload['mime_type'] == 'audio/mp4'
    assert payload['url'].endswith('.m4a')
