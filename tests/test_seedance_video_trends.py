from __future__ import annotations

import pytest
from app.services.trends import TrendService


def recipe():
    return {
        "model_id": "seedance-2.5", "prompt": "Animate @Image1 following @Video1",
        "preview_url": "https://preview.example/result.mp4",
        "media_type": "video", "input_mode": "image", "min_references": 1, "max_references": 1,
        "parameters": {"duration": 5, "resolution": "720p", "aspect_ratio": "9:16"},
    }


def test_seedance_recipe_infers_user_video_slot_without_using_preview():
    payload = recipe()
    payload["preview_url"] = "https://preview.example/result.mp4"
    normalized = TrendService.normalize_recipe("Video trend", payload)
    assert normalized["video_reference_count"] == 1
    assert normalized["min_references"] == normalized["max_references"] == 1
    assert "reference_video_urls" not in normalized["parameters"]


@pytest.mark.parametrize("prompt", ["Follow @Video11", "Follow @Video999999"])
def test_template_rejects_video_count_above_current_provider_limit(prompt):
    payload = recipe()
    payload["prompt"] = prompt
    with pytest.raises(ValueError):
        TrendService.normalize_recipe("Video trend", payload)


@pytest.mark.asyncio
async def test_video_trend_admin_publish_user_run_freeze_and_repeat(monkeypatch, tmp_path):
    import json
    import subprocess
    import uuid
    from decimal import Decimal
    from unittest.mock import AsyncMock

    import httpx
    from fastapi import Request
    from sqlalchemy import select

    from app.api.v1 import trends as api
    from app.core.config import settings
    from app.db.models import AdminAccount, Generation, User, WalletTransaction
    from app.db.session import SessionFactory
    from app.db.reference_models import UserReference
    from app.providers.neironych_video import NeironychVideoClient
    from app.services.neironych_generation_provider import NeironychGenerationProviderService
    from app.providers.neironych_submission import SNAPSHOT_KEY
    from app.services.reference_resolver import ReferenceResolver
    from app.services.wallet import WalletService

    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "public_base_url", "https://media.example")
    async def configured(*args, **kwargs):
        return ("neironych", "nexus", "kie"), 1
    monkeypatch.setattr("app.services.generations.configured_route", configured)
    path = tmp_path / "source.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", "color=c=blue:s=720x1280:r=24", "-t", "2", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-y", str(path),
    ], check=True)
    video = "https://media.example/uploads/refs/source.mp4"
    payload = recipe()
    payload.update(prompt="Follow motion in @Video1", input_mode="none", min_references=0, max_references=0)
    posts = []

    def accepted(request):
        posts.append(request)
        body = json.loads(request.content)
        assert body["reference_videos"] == [{"url": video}]
        assert "preview" not in str(body)
        return httpx.Response(202, json={"request_id": "synthetic-video-" + str(uuid.uuid4())})

    request = Request({"type": "http", "headers": []})
    async with SessionFactory() as session:
        admin_user = User(telegram_id=uuid.uuid4().int % 10**14)
        customer = User(telegram_id=uuid.uuid4().int % 10**14)
        session.add_all([admin_user, customer])
        await session.flush()
        session.add(AdminAccount(user_id=admin_user.id, role="admin"))
        session.add(UserReference(
            user_id=customer.id, source_url=video, kind="video", status="ready",
            size_bytes=path.stat().st_size, duration_ms=2000, width=720, height=1280,
            container="mov,mp4", video_codec="h264", probe_status="ready",
        ))
        await WalletService.credit(session, user_id=customer.id, amount=Decimal("10000"),
                                   kind="test", idempotency_key=f"seed:{customer.id}")
        await session.commit()
        created = await api.inline_admin_trend_create(
            api.InlineTrendWriteRequest(title="Synthetic video trend", payload=payload),
            request, admin_user, session, idempotency_key=f"trend:{uuid.uuid4()}",
        )
        tid = uuid.UUID(created["id"])
        public = await api.get_trend(tid, customer, session)
        assert public["reference_requirements"]["kind"] == "video"
        assert public["reference_requirements"]["video"] == {"min": 1, "max": 1}
        assert "prompt" not in public and "parameters" not in public
        redis = AsyncMock()
        with pytest.raises(Exception, match="requires 1 video"):
            await TrendService.run(session, redis, user_id=customer.id, trend_id=tid, reference_urls=[])
        with pytest.raises(Exception, match="Upload and verify"):
            await TrendService.run(
                session, redis, user_id=admin_user.id, trend_id=tid,
                reference_urls=[], video_reference_urls=[video], aspect_ratio="9:16",
            )
        media = await session.scalar(select(UserReference).where(
            UserReference.user_id == customer.id, UserReference.source_url == video
        ))
        for field, bad in [("duration_ms", 31000), ("size_bytes", 201 * 1024 * 1024)]:
            previous = getattr(media, field)
            setattr(media, field, bad)
            await session.flush()
            with pytest.raises(ValueError):
                await TrendService.run(
                    session, redis, user_id=customer.id, trend_id=tid,
                    reference_urls=[], video_reference_urls=[video], aspect_ratio="9:16",
                )
            setattr(media, field, previous)
            await session.flush()
        charges = (await session.scalars(select(WalletTransaction).where(
            WalletTransaction.user_id == customer.id, WalletTransaction.kind == "generation"
        ))).all()
        assert charges == []
        for _ in range(2):
            generation, _ = await TrendService.run(
                session, redis, user_id=customer.id, trend_id=tid,
                reference_urls=[], video_reference_urls=[video], aspect_ratio="9:16",
            )
            assert generation.parameters["reference_video_urls"] == [video]
            assert generation.cost_rox == Decimal(public["cost_rox"])
            context = ReferenceResolver.generation_context(generation)
            assert context.reference_videos == [video]
            assert context.provider_input["reference_video_urls"] == [video]
            assert generation.provider == "neironych"
            async with httpx.AsyncClient(
                base_url="https://gateway.example", transport=httpx.MockTransport(accepted)
            ) as http:
                monkeypatch.setattr(
                    "app.services.neironych_generation_provider.NeironychVideoClient",
                    lambda *args: NeironychVideoClient("test", "https://gateway.example", client=http),
                )
                # Production base is frozen too; only the HTTP transport is synthetic.
                row = await NeironychGenerationProviderService.submit(session, generation.id)
                assert row.status == "generating"
                frozen = row.parameters[SNAPSHOT_KEY]["body_json"]
                assert json.loads(frozen)["reference_videos"] == [{"url": video}]
                await NeironychGenerationProviderService.submit(session, generation.id)
            transactions = (await session.scalars(select(WalletTransaction).where(
                WalletTransaction.reference_id == str(generation.id)
            ))).all()
            assert len(transactions) == 1 and transactions[0].kind == "generation"
        assert len(posts) == 2  # Two explicit user actions; no duplicate provider POST.
        assert (await session.get(Generation, generation.id)).action_type == "trend"


@pytest.mark.asyncio
async def test_structural_video_slot_preflight_cannot_admit_unverified_runtime_media():
    from app.db.session import SessionFactory
    from app.services.generations import GenerationService

    payload = recipe()
    payload.update(prompt="Follow @Video1", input_mode="none", min_references=0, max_references=0)
    async with SessionFactory() as session:
        normalized = await TrendService.validate_recipe(session, title="Slots", payload=payload)
        parameters = TrendService._parameters_with_references(normalized, [], template=True)
        with pytest.raises(ValueError, match="duration must be verified"):
            await GenerationService.prepare_request(
                session, model_id="seedance-2.5", prompt=payload["prompt"],
                parameters=parameters, billing_seconds=5,
            )
