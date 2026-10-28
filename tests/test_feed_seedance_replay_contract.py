from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.api.v1.generations import _generation_view, _recreate_payload_for_generation
from app.db.models import Generation
from app.services.feed_remix import FeedRemixReferenceError, FeedRemixService
from app.services.feed_seedance_replay import (
    PRIVATE_AUTHOR_REPLAY_MARKER,
    build_seedance_motion_identity_prompt,
    canonicalize_seedance_author_prompt,
    is_private_seedance_author_replay,
    seedance_identity_requirements,
    seedance_motion_original_prompt_max_chars,
)
from app.services.model_routing import resolve_model_request
from app.services.neironych_video_contracts import normalize_neironych_video_input
from app.services.seedance25_contract import normalize_seedance25_input
from app.services.generation_action_contexts import build_action_context_payload
from app.services.generation_actions import GenerationActionService


def test_seedance_identity_requirements_always_request_a_viewer_photo() -> None:
    assert seedance_identity_requirements(source_image_count=0) == {
        "image_count": 1,
        "video_count": 0,
        "audio_count": 0,
        "required": True,
    }
    assert seedance_identity_requirements(source_image_count=2)["image_count"] == 2


def test_seedance_motion_prompt_assigns_author_video_and_viewer_identity_roles() -> None:
    prompt = build_seedance_motion_identity_prompt(
        "A person turns toward the camera",
        identity_count=2,
    )

    assert "@Video1 is the authoritative source for motion" in prompt
    assert "@Image1" in prompt
    assert "@Image2" in prompt
    assert "identity" in prompt.lower()
    assert prompt.endswith("A person turns toward the camera")


@pytest.mark.parametrize("identity_count", [0, -1])
def test_seedance_motion_prompt_requires_identity_photos(identity_count: int) -> None:
    with pytest.raises(ValueError, match="identity photo"):
        build_seedance_motion_identity_prompt("Move naturally", identity_count=identity_count)


def test_seedance_motion_prompt_reserves_space_for_role_instructions() -> None:
    maximum = seedance_motion_original_prompt_max_chars(identity_count=1)

    assert len(build_seedance_motion_identity_prompt("x" * maximum, identity_count=1)) == 30_000
    with pytest.raises(ValueError, match="too long"):
        build_seedance_motion_identity_prompt("x" * (maximum + 1), identity_count=1)
    with pytest.raises(ValueError, match="UTF-8"):
        build_seedance_motion_identity_prompt("я" * 20_000, identity_count=1)


def test_seedance_author_replay_reaches_provider_as_mixed_reference_payload() -> None:
    prompt = build_seedance_motion_identity_prompt(
        "A person turns toward the camera",
        identity_count=1,
    )
    routed = resolve_model_request(
        "seedance-2.5",
        {
            "duration": 10,
            "resolution": "720p",
            "aspect_ratio": "9:16",
            "reference_images": ["https://example.invalid/viewer.jpg"],
            "reference_videos": ["https://example.invalid/author-motion.mp4"],
            "reference_audio_urls": ["https://example.invalid/author-audio.mp3"],
        },
    )
    kie_validated = normalize_seedance25_input({**routed.parameters, "prompt": prompt})
    provider_payload = normalize_neironych_video_input(
        "seedance-2.5",
        kie_validated,
    )

    assert provider_payload["reference_images"] == [
        {"url": "https://example.invalid/viewer.jpg"}
    ]
    assert provider_payload["reference_videos"] == [
        {"url": "https://example.invalid/author-motion.mp4"}
    ]
    assert provider_payload["reference_audios"] == [
        {"url": "https://example.invalid/author-audio.mp3"}
    ]
    assert "omni_reference_task_type" not in provider_payload
    assert "@Video1 is the authoritative source for motion" in provider_payload["prompt"]


def test_seedance_replay_replaces_author_identity_but_restores_author_motion() -> None:
    author_photo = "https://example.invalid/author.jpg"
    author_video = "https://example.invalid/author-motion.mp4"
    author_audio = "https://example.invalid/author-audio.mp3"
    source = Generation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        kind="reference_to_video",
        status="succeeded",
        prompt="Original prompt",
        result_url="https://example.invalid/rendered.mp4",
        cost_rox=Decimal("70"),
        provider="neironych",
        parameters={
            "_model_id": "seedance-2.5",
            "reference_image_urls": [author_photo],
            "reference_video_urls": [author_video],
            "reference_audio_urls": [author_audio],
            "omni_reference_task_type": "edit",
            "duration": 10,
        },
    )

    parameters, videos = FeedRemixService._seedance_replay_parameters(
        {"duration": 10, "omni_reference_task_type": "edit"},
        source=source,
        viewer_references={
            "image": ["https://example.invalid/viewer.jpg"],
            "video": [],
            "audio": [],
        },
        expected_image_count=1,
    )

    assert parameters["reference_images"] == ["https://example.invalid/viewer.jpg"]
    assert parameters["reference_videos"] == [author_video]
    assert parameters["reference_audio_urls"] == [author_audio]
    assert "omni_reference_task_type" not in parameters
    assert author_photo not in str(parameters)
    assert str(source.result_url) not in str(parameters)
    assert videos == [author_video]

    source.source_feed_gen_id = uuid.uuid4()
    with pytest.raises(FeedRemixReferenceError, match="cannot be used"):
        FeedRemixService._assert_root_source(source)
    source.source_feed_gen_id = None

    with pytest.raises(FeedRemixReferenceError, match="exactly 1"):
        FeedRemixService._seedance_replay_parameters(
            {"duration": 10},
            source=source,
            viewer_references={
                "image": [
                    "https://example.invalid/viewer.jpg",
                    "https://example.invalid/viewer-extra.jpg",
                ],
                "video": [],
                "audio": [],
            },
            expected_image_count=1,
        )


def test_seedance_legacy_combined_tag_is_resolved_before_identity_photo_is_added() -> None:
    prompt = canonicalize_seedance_author_prompt(
        "Keep the movement from @Image1",
        source_image_count=0,
        source_video_count=1,
        source_audio_count=0,
    )

    assert prompt == "Keep the movement from @Video1"
    wrapped = build_seedance_motion_identity_prompt(prompt, identity_count=1)
    assert "movement from @Video1" in wrapped
    assert "@Image1 are the authoritative identity references" in wrapped


def test_owned_history_redacts_private_seedance_author_recipe() -> None:
    now = datetime.now(UTC)
    author_video = "https://example.invalid/author-motion.mp4"
    author_audio = "https://example.invalid/author-audio.mp3"
    generation = Generation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        kind="reference_to_video",
        status="succeeded",
        prompt="@Video1 role wrapper with hidden author prompt",
        result_url="https://example.invalid/result.mp4",
        cost_rox=Decimal("70"),
        provider="neironych",
        parameters={
            "_model_id": "seedance-2.5",
            "_model_title": "Seedance 2.5",
            "_model_family": "seedance",
            "_operation": "multimodal_video",
            "_media_type": "video",
            "_retail_cost_rox": "70",
            PRIVATE_AUTHOR_REPLAY_MARKER: True,
            "reference_image_urls": ["https://example.invalid/viewer.jpg"],
            "reference_video_urls": [author_video],
            "reference_audio_urls": [author_audio],
            "duration": 10,
        },
        source_feed_gen_id=uuid.uuid4(),
        parent_generation_id=uuid.uuid4(),
        action_type="remix",
        error=f"Provider rejected {author_video} and {author_audio}",
        created_at=now,
        updated_at=now,
    )

    view = _generation_view(generation)

    assert view["prompt"] == ""
    assert view["prompt_hidden"] is True
    assert view["prompt_actions_allowed"] is False
    assert author_video not in str(view)
    assert author_audio not in str(view)
    assert view["error"] == "Не удалось создать повтор. Попробуйте ещё раз."
    assert view["settings"]["reference_image_urls"] == [
        "https://example.invalid/viewer.jpg"
    ]
    with pytest.raises(HTTPException) as exc_info:
        _recreate_payload_for_generation(generation)
    assert exc_info.value.status_code == 409

    assert [item.id for item in GenerationActionService.available_actions(generation)] == [
        "publish"
    ]
    assert GenerationActionService.parent_references(generation) == ([], [])
    action_context = build_action_context_payload(generation, "publish")
    assert action_context["generation"]["prompt"] == ""
    assert action_context["generation"]["prompt_hidden"] is True
    assert action_context["source_references"] == {"images": [], "videos": []}
    assert author_video not in str(action_context)
    assert author_audio not in str(action_context)

    historical = Generation(
        id=uuid.uuid4(),
        user_id=generation.user_id,
        kind=generation.kind,
        status="succeeded",
        prompt="Visible historical remix prompt",
        result_url=generation.result_url,
        cost_rox=generation.cost_rox,
        provider=generation.provider,
        parameters={
            key: value
            for key, value in dict(generation.parameters or {}).items()
            if key != PRIVATE_AUTHOR_REPLAY_MARKER
        },
        source_feed_gen_id=uuid.uuid4(),
        action_type="remix",
        created_at=now,
        updated_at=now,
    )
    assert is_private_seedance_author_replay(historical) is False
    assert _generation_view(historical)["prompt"] == "Visible historical remix prompt"
    assert {item.id for item in GenerationActionService.available_actions(historical)} != {
        "publish"
    }
