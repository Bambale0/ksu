from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.generations import GenerationService
from app.services.trends import TrendRecipeError, TrendService
from app.services.trend_references import extract_reference_slots
from app.services.reference_static import ReferenceStaticStorage


def payload(mode="strict"):
    return {
        "model_id": "nano-banana-pro",
        "prompt": "Image1 персонаж, @image_2 одежда",
        "preview_url": "https://cdn.example/preview.jpg",
        "input_mode": "image",
        "parameters": {"aspect_ratio": "1:1", "resolution": "1K"},
        "reference_schema": {
            "mode": mode,
            "slots": [
                {
                    "id": "image_1",
                    "label": "Персонаж",
                    "description": "Чёткое фото лица",
                    "kind": "image",
                    "source": "user",
                    "order": 0,
                    "required": True,
                },
                {
                    "id": "image_2",
                    "label": "Одежда",
                    "description": "Нужный образ",
                    "kind": "image",
                    "source": "user",
                    "order": 1,
                    "required": True,
                },
            ],
        },
    }


def test_strict_named_recipe_controls_count_without_changing_legacy_ranges():
    raw = payload()
    recipe = TrendService.normalize_recipe("Образ", raw)
    assert recipe["min_references"] == recipe["max_references"] == 2
    assert recipe["reference_schema"]["slots"][1]["label"] == "Одежда"
    del raw["reference_schema"]
    raw.update(min_references=1, max_references=4)
    legacy = TrendService.normalize_recipe("Старый образ", raw)
    assert (legacy["min_references"], legacy["max_references"]) == (1, 4)


@pytest.mark.asyncio
async def test_missing_named_slot_rejected_before_generation(monkeypatch):
    item = SimpleNamespace(id=uuid.uuid4(), title="Образ", payload=payload(), is_active=True)
    session = AsyncMock()
    session.get.return_value = item
    create = AsyncMock()
    monkeypatch.setattr(GenerationService, "create", create)
    with pytest.raises(TrendRecipeError):
        await TrendService.run(
            session,
            AsyncMock(),
            user_id=uuid.uuid4(),
            trend_id=item.id,
            reference_urls=["https://cdn.example/person.jpg"],
            aspect_ratio="1:1",
        )
    create.assert_not_awaited()


def test_prompt_discovery_is_explicit_deduplicated_and_does_not_match_words():
    slots = extract_reference_slots(
        "Image1 person, @image_2 clothes, @IMAGE1 again, preImage9, Image2x, @Video1"
    )
    assert [s["id"] for s in slots] == ["image_1", "image_2", "video_1"]
    assert "reference_schema" not in TrendService.normalize_recipe(
        "Legacy", {k: v for k, v in payload().items() if k != "reference_schema"}
    )


@pytest.mark.asyncio
async def test_video_slot_rejects_uploaded_audio_disguised_as_video_before_generation(monkeypatch):
    raw = {
        "model_id": "seedance-2.5",
        "prompt": "@Video1 motion",
        "preview_url": "https://cdn.example/preview.jpg",
        "parameters": {"duration": 5, "aspect_ratio": "9:16", "resolution": "720p"},
        "reference_schema": {
            "mode": "strict",
            "slots": [
                {
                    "id": "video_1",
                    "kind": "video",
                    "source": "user",
                    "label": "Движение",
                    "order": 0,
                    "required": True,
                }
            ],
        },
    }
    item = SimpleNamespace(id=uuid.uuid4(), title="Motion", is_active=True, payload=raw)
    session = AsyncMock()
    session.get.return_value = item
    session.scalar.return_value = SimpleNamespace(
        source_url="https://roxy.example/video.mp4", video_codec=None, duration_ms=5000
    )
    monkeypatch.setattr(ReferenceStaticStorage, "local_url_exists", lambda _: True)
    create = AsyncMock()
    monkeypatch.setattr(GenerationService, "create", create)
    with pytest.raises(TrendRecipeError, match="видео"):
        await TrendService.run(
            session,
            AsyncMock(),
            user_id=uuid.uuid4(),
            trend_id=item.id,
            reference_urls=[],
            reference_inputs=[
                {"slot_id": "video_1", "kind": "video", "url": "https://roxy.example/video.mp4"}
            ],
            aspect_ratio="9:16",
        )
    create.assert_not_awaited()


def test_range_permits_only_optional_trailing_slots_without_number_shift():
    raw = payload("range")
    raw["prompt"] = "Image1 персонаж"
    raw["reference_schema"]["slots"][1]["required"] = False
    recipe = TrendService.normalize_recipe("Образ", raw)
    assert (recipe["min_references"], recipe["max_references"]) == (1, 2)
    raw["reference_schema"]["slots"][0]["required"] = False
    raw["reference_schema"]["slots"][1]["required"] = True
    with pytest.raises(TrendRecipeError, match="последними"):
        TrendService.normalize_recipe("Образ", raw)


@pytest.mark.parametrize("mutation", ["order", "id", "required", "capacity", "prompt"])
def test_invalid_schema_cannot_be_published(mutation):
    raw = payload()
    if mutation == "order":
        raw["reference_schema"]["slots"][0]["order"] = 1
    if mutation == "id":
        raw["reference_schema"]["slots"][1]["id"] = "image_1"
    if mutation == "required":
        raw["reference_schema"]["slots"][1]["required"] = False
    if mutation == "capacity":
        raw["reference_schema"]["slots"] = [
            dict(raw["reference_schema"]["slots"][0], id=f"image_{i + 1}", order=i)
            for i in range(5)
        ]
    if mutation == "prompt":
        raw["prompt"] += " Image3"
    with pytest.raises(TrendRecipeError):
        TrendService.normalize_recipe("Образ", raw)


@pytest.mark.asyncio
async def test_named_run_merges_preset_by_role_and_validates_personal_fields(monkeypatch):
    raw = payload()
    raw["prompt"] += " {{Возраст}}"
    raw["reference_schema"]["slots"][1].update(
        source="admin", url="https://roxy.example/preset.jpg"
    )
    item = SimpleNamespace(id=uuid.uuid4(), title="Образ", payload=raw, is_active=True)
    owned = SimpleNamespace(
        source_url="https://roxy.example/user.jpg", width=100, height=100, duration_ms=None
    )
    preset = SimpleNamespace(
        source_url="https://roxy.example/preset.jpg",
        status="ready",
        content_type="image/jpeg",
        width=100,
        height=100,
        size_bytes=100,
    )
    session = AsyncMock()
    session.get.return_value = item
    monkeypatch.setattr(ReferenceStaticStorage, "local_url_exists", lambda _: True)
    session.scalar.side_effect = [owned, preset]
    create = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
    monkeypatch.setattr(GenerationService, "create", create)
    inputs = [{"slot_id": "image_1", "kind": "image", "url": owned.source_url}]
    with pytest.raises(TrendRecipeError, match="Возраст"):
        await TrendService.run(
            session,
            AsyncMock(),
            user_id=uuid.uuid4(),
            trend_id=item.id,
            reference_urls=[],
            reference_inputs=inputs,
            aspect_ratio="1:1",
        )
    create.assert_not_awaited()
    session.scalar.side_effect = [owned, preset, item]
    await TrendService.run(
        session,
        AsyncMock(),
        user_id=uuid.uuid4(),
        trend_id=item.id,
        reference_urls=[],
        reference_inputs=inputs,
        user_values={"Возраст": "25"},
        aspect_ratio="1:1",
    )
    assert create.await_args.kwargs["parameters"]["image_input"] == [
        owned.source_url,
        preset.source_url,
    ]
    assert create.await_args.kwargs["prompt"].endswith(" 25")
    assert "reference_schema" not in create.await_args.kwargs["parameters"]


@pytest.mark.asyncio
async def test_public_schema_hides_preset_urls_and_private_prompt(monkeypatch):
    raw = payload()
    raw["reference_schema"]["slots"][1].update(
        source="admin", url="https://roxy.example/private-preset.jpg"
    )
    now = datetime.now(UTC)
    item = SimpleNamespace(
        id=uuid.uuid4(), title="Образ", payload=raw, created_at=now, updated_at=now
    )
    from app.services.model_catalog import ModelCatalog

    monkeypatch.setattr(
        GenerationService,
        "prepare_template_request",
        AsyncMock(
            return_value=(ModelCatalog.get("nano-banana-pro"), {}, Decimal("25"), None, None)
        ),
    )
    view = await TrendService.public_view(AsyncMock(), item)
    assert view["reference_requirements"]["image"] == {"min": 1, "max": 1}
    assert view["reference_schema"]["slots"][1]["source"] == "admin"
    assert "private-preset" not in repr(view)
    assert "prompt" not in view and "parameters" not in view


@pytest.mark.asyncio
async def test_range_gap_cannot_shift_later_image(monkeypatch):
    raw = payload("range")
    raw["prompt"] = "portrait"
    for slot in raw["reference_schema"]["slots"]:
        slot["required"] = False
    item = SimpleNamespace(id=uuid.uuid4(), title="Образ", payload=raw, is_active=True)
    session = AsyncMock()
    session.get.return_value = item
    create = AsyncMock()
    monkeypatch.setattr(GenerationService, "create", create)
    with pytest.raises(TrendRecipeError, match="без пропусков"):
        await TrendService.run(
            session,
            AsyncMock(),
            user_id=uuid.uuid4(),
            trend_id=item.id,
            reference_urls=[],
            reference_inputs=[
                {"slot_id": "image_2", "kind": "image", "url": "https://roxy.example/2.jpg"}
            ],
            aspect_ratio="1:1",
        )
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_named_media_must_be_owned_and_verified_before_billing(monkeypatch):
    item = SimpleNamespace(id=uuid.uuid4(), title="Образ", payload=payload(), is_active=True)
    session = AsyncMock()
    session.get.return_value = item
    session.scalar.return_value = None
    create = AsyncMock()
    monkeypatch.setattr(GenerationService, "create", create)
    with pytest.raises(TrendRecipeError, match="проверенн"):
        await TrendService.run(
            session,
            AsyncMock(),
            user_id=uuid.uuid4(),
            trend_id=item.id,
            reference_urls=[],
            reference_inputs=[
                {"slot_id": "image_1", "kind": "image", "url": "https://cdn.example/a.jpg"},
                {"slot_id": "image_2", "kind": "image", "url": "https://cdn.example/b.jpg"},
            ],
            aspect_ratio="1:1",
        )
    create.assert_not_awaited()


@pytest.mark.parametrize("change", ["duplicate", "order", "type", "extra"])
async def test_invalid_named_identity_never_reaches_generation(monkeypatch, change):
    item = SimpleNamespace(id=uuid.uuid4(), title="Образ", payload=payload(), is_active=True)
    session = AsyncMock()
    session.get.return_value = item
    create = AsyncMock()
    monkeypatch.setattr(GenerationService, "create", create)
    inputs = [
        {"slot_id": f"image_{i}", "kind": "image", "url": f"https://cdn.example/{i}.jpg"}
        for i in (1, 2)
    ]
    if change == "duplicate":
        inputs[1]["slot_id"] = "image_1"
    if change == "order":
        inputs.reverse()
    if change == "type":
        inputs[0]["kind"] = "video"
    if change == "extra":
        inputs.append({"slot_id": "image_3", "kind": "image", "url": "https://cdn.example/3.jpg"})
    with pytest.raises(TrendRecipeError):
        await TrendService.run(
            session,
            AsyncMock(),
            user_id=uuid.uuid4(),
            trend_id=item.id,
            reference_urls=[],
            reference_inputs=inputs,
            aspect_ratio="1:1",
        )
    create.assert_not_awaited()
