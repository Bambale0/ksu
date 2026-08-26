from __future__ import annotations

import uuid
from decimal import Decimal

from app.db.models import Generation
from app.services.generation_actions import GenerationActionService
from app.services.feed_static import FeedStaticStorage


def _video_generation() -> Generation:
    result_url = "https://cdn.example/generated-video.mp4"
    return Generation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        kind="video",
        status="succeeded",
        prompt="cinematic clip",
        cost_rox=Decimal("25.00"),
        result_url=result_url,
        parameters={
            "_model_id": "kling-3.0",
            "_media_type": "video",
            "_result_urls": [result_url],
        },
    )


def test_completed_video_exposes_publish_action() -> None:
    generation = _video_generation()
    actions = {item.id: item for item in GenerationActionService.available_actions(generation)}

    assert "publish" in actions
    assert actions["publish"].derivative is False
    assert actions["publish"].label == "📤 Опубликовать"


def test_feed_static_storage_accepts_generated_video_payloads() -> None:
    mp4 = b"\x00\x00\x00\x18ftypisom0000roxy-video"
    webm = b"\x1aE\xdf\xa3roxy-video"

    assert FeedStaticStorage._magic(mp4) == (".mp4", "video/mp4")  # noqa: SLF001
    assert FeedStaticStorage._magic(webm) == (".webm", "video/webm")  # noqa: SLF001
