"""Exercise the browser media boundary, not only the workflow DTO shape."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api.v1.media import router as media_router
from app.db.admin_models import AdminTrend
from app.db.models import AdminAccount, Generation, User
from app.db.session import SessionFactory
from app.db.trend_workflow_models import TrendWorkflowRun, TrendWorkflowStep
from app.services.media_assets import MediaAssetService
from app.services.trend_workflows import TrendWorkflowService


@pytest.mark.asyncio
async def test_ready_workflow_photo_is_viewable_without_publication(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_LOCAL_ROOT", str(tmp_path / "private-media"))
    image_path = tmp_path / "synthetic.png"
    Image.new("RGB", (16, 16), (80, 80, 80)).save(image_path)
    expected_bytes = image_path.read_bytes()
    recipe = {
        "schema_version": 2,
        "workflow_type": "sequential_photo_video",
        "preview_url": "https://example.invalid/preview.jpg",
        "description": "Synthetic workflow",
        "steps": [
            {"id": "photo", "kind": "image", "title": "Photo", "instructions": "", "inputs": [],
             "model_id": "nano-banana-pro", "prompt": "Synthetic photo",
             "parameters": {"aspect_ratio": "9:16", "resolution": "1K"}},
            {"id": "video", "kind": "video", "title": "Video", "instructions": "", "inputs": [],
             "model_id": "seedance-2.5", "prompt": "Animate the photo",
             "parameters": {"duration": 5, "resolution": "720p", "aspect_ratio": "9:16"},
             "bindings": [{"from": "photo.output_image", "to": "reference_image_urls"}]},
        ],
    }
    async with SessionFactory() as session:
        user = User(telegram_id=uuid.uuid4().int % (2**62), first_name="Synthetic media QA")
        session.add(user)
        await session.flush()
        account = AdminAccount(user_id=user.id, role="admin")
        session.add(account)
        await session.flush()
        trend = AdminTrend(title="Private workflow fixture", payload=recipe, created_by_admin_id=account.id)
        session.add(trend)
        await session.flush()
        generation = Generation(
            user_id=user.id, kind="image", status="succeeded", prompt="Synthetic fixture",
            cost_rox=Decimal("0.00"), provider="kie", action_type="trend",
            parameters={"_media_type": "image", "_model_id": "nano-banana-pro"},
            result_url="https://expired.invalid/provider-result.png", publication_scope="private",
        )
        session.add(generation)
        await session.flush()
        asset = await MediaAssetService.persist_ready_local_file(
            session, generation, path=image_path, content_type="image/png",
            source_url=generation.result_url,
        )
        run = TrendWorkflowRun(
            user_id=user.id, trend_id=trend.id, recipe_snapshot=recipe,
            command_key=str(uuid.uuid4()), request_hash="0" * 64, status="step1_ready",
        )
        session.add(run)
        await session.flush()
        session.add_all([
            TrendWorkflowStep(
                workflow_id=run.id, step_key="photo", ordinal=0, kind="image", status="ready",
                generation_id=generation.id, media_asset_id=asset.id, attempts=1,
            ),
            TrendWorkflowStep(workflow_id=run.id, step_key="video", ordinal=1, kind="video"),
        ])
        await session.commit()
        run_id, user_id, asset_id = run.id, user.id, asset.id

    async with SessionFactory() as session:
        view = await TrendWorkflowService.public_view(session, run_id=run_id, user_id=user_id)
    assert view["steps"][0]["status"] == "ready"
    media = view["steps"][0]["media"]
    app = FastAPI()
    app.include_router(media_router, prefix="/api/v1")
    async with AsyncClient(transport=ASGITransport(app), base_url="http://workflow.test") as client:
        private_response = await client.get(media["url"])
        assert private_response.status_code == 200, private_response.text
        assert private_response.content == expected_bytes
        assert private_response.headers["content-type"].startswith("image/png")
        assert (await client.get(f"/api/v1/media/{asset_id}/public")).status_code == 404
        for option in view["steps"][0]["media_options"]:
            assert (await client.get(option["url"])).status_code == 200
