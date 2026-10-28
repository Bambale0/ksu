from __future__ import annotations

import io
import json
import random
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from app.db.models import Generation, User
from app.db.session import SessionFactory
from app.providers.neironych_image import NeironychImageResult
from app.providers.neironych_video import NeironychProviderError
from app.services.neironych_generation_provider import NeironychGenerationProviderService


class BalanceFailImageClient:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    async def aclose(self) -> None:
        pass

    async def create_nano_banana_pro(self, **_kwargs: object) -> object:
        raise NeironychProviderError(
            "Neironych API HTTP 402: insufficient_balance",
            status_code=402,
        )


class ConflictImageClient:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    async def aclose(self) -> None:
        pass

    async def create_nano_banana_pro(self, **_kwargs: object) -> object:
        raise NeironychProviderError(
            "Neironych API HTTP 409: request_already_submitted",
            status_code=409,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code,expected",
    [
        (400, "provider_rejected_request", "Провайдер отклонил параметры или медиа"),
        (402, "insufficient_balance", "У провайдера временно недостаточно средств"),
    ],
)
async def test_terminal_400_402_persists_only_safe_user_reason(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    code: str,
    expected: str,
) -> None:
    class RejectingClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def create_video(self, **_kwargs: object) -> str:
            raise NeironychProviderError(
                "private prompt https://private.example/ref.png?token=secret-value",
                status_code=status,
                error_code=code,
                payload={"error": {"message": "private prompt secret-value"}},
            )

    monkeypatch.setattr(
        "app.services.neironych_generation_provider.NeironychVideoClient",
        RejectingClient,
    )
    generation = await _generation(
        model_id="seedance-2.5",
        route=["neironych"],
        parameters={"prompt": "scene", "duration": 5, "resolution": "720p"},
    )

    async with SessionFactory() as session:
        result = await NeironychGenerationProviderService.submit(session, generation.id)
        assert result.status == "failed"
        assert expected in str(result.error)
        assert "private prompt" not in str(result.error)
        assert "secret-value" not in str(result.error)
        assert "private.example" not in str(result.error)


async def _generation(*, model_id: str, route: list[str], parameters: dict[str, object]) -> Generation:
    async with SessionFactory() as session:
        user = User(
            telegram_id=random.randint(8_100_000_000_000, 8_999_999_999_999),
            first_name="Provider routing",
        )
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_image" if model_id == "nano-banana-pro" else "text_to_video",
            status="queued",
            prompt=str(parameters.get("prompt") or "test"),
            cost_rox=Decimal("0"),
            provider="neironych",
            parameters={
                **parameters,
                "_model_id": model_id,
                "_provider_route": route,
                "_provider_route_index": 0,
            },
        )
        session.add(generation)
        await session.commit()
        await session.refresh(generation)
        return generation


@pytest.mark.asyncio
async def test_nano_balance_rejection_falls_back_to_nexus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.neironych_generation_provider.NeironychImageClient",
        BalanceFailImageClient,
    )
    generation = await _generation(
        model_id="nano-banana-pro",
        route=["neironych", "nexus"],
        parameters={
            "prompt": "portrait",
            "aspect_ratio": "1:1",
            "resolution": "1K",
        },
    )

    async with SessionFactory() as session:
        result = await NeironychGenerationProviderService.submit(session, generation.id)
        assert result.provider == "nexus"
        assert result.status == "retry"
        assert result.external_id is None
        assert result.parameters["_provider_route_index"] == 1


@pytest.mark.asyncio
async def test_seedance_generate_audio_false_is_sent_to_neironych(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class VideoClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def create_video(self, **kwargs: object) -> str:
            captured.update(kwargs)
            return "neironych-silent-video-1"

    monkeypatch.setattr(
        "app.services.neironych_generation_provider.NeironychVideoClient",
        VideoClient,
    )
    generation = await _generation(
        model_id="seedance-2.5",
        route=["neironych", "kie"],
        parameters={
            "prompt": "cinematic",
            "aspect_ratio": "9:16",
            "resolution": "720p",
            "duration": 5,
            "generate_audio": False,
        },
    )

    async with SessionFactory() as session:
        result = await NeironychGenerationProviderService.submit(session, generation.id)
        assert result.provider == "neironych"
        assert result.status == "generating"
        assert result.external_id == "neironych-silent-video-1"
        assert result.parameters["_provider_route_index"] == 0

    assert json.loads(str(captured["request_body"]))["generate_audio"] is False


@pytest.mark.asyncio
async def test_nano_ambiguous_sync_result_never_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.neironych_generation_provider.NeironychImageClient",
        ConflictImageClient,
    )
    generation = await _generation(
        model_id="nano-banana-pro",
        route=["neironych", "nexus"],
        parameters={
            "prompt": "portrait",
            "aspect_ratio": "1:1",
            "resolution": "1K",
        },
    )

    async with SessionFactory() as session:
        result = await NeironychGenerationProviderService.submit(session, generation.id)
        assert result.provider == "neironych"
        assert result.status == "submitting"
        assert result.external_id is None
        assert result.parameters["_provider_route_index"] == 0
        assert result.parameters["_submission_uncertain"] is True


class SuccessImageClient:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    async def aclose(self) -> None:
        pass

    async def create_nano_banana_pro(self, **_kwargs: object) -> NeironychImageResult:
        buffer = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(buffer, format="JPEG")
        return NeironychImageResult(content=buffer.getvalue())


@pytest.mark.asyncio
async def test_nano_png_request_is_converted_before_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.neironych_generation_provider.NeironychImageClient",
        SuccessImageClient,
    )
    captured: dict[str, object] = {}

    async def fake_complete(
        cls: type[NeironychGenerationProviderService],
        session: object,
        generation_id: object,
        *,
        path: Path,
        content_type: str,
        source_url: str,
    ) -> Generation:
        data = path.read_bytes()
        captured["suffix"] = path.suffix
        captured["content_type"] = content_type
        captured["source_url"] = source_url
        captured["png_signature"] = data[:8]
        async with SessionFactory() as real_session:
            generation = await real_session.get(Generation, generation_id)
            assert generation is not None
            return generation

    monkeypatch.setattr(
        NeironychGenerationProviderService,
        "_complete_local_file",
        classmethod(fake_complete),
    )
    generation = await _generation(
        model_id="nano-banana-pro",
        route=["neironych", "nexus"],
        parameters={
            "prompt": "portrait",
            "aspect_ratio": "1:1",
            "resolution": "1K",
            "output_format": "png",
        },
    )

    async with SessionFactory() as session:
        await NeironychGenerationProviderService.submit(session, generation.id)

    assert captured["suffix"] == ".png"
    assert captured["content_type"] == "image/png"
    assert str(captured["source_url"]).endswith(".png")
    assert captured["png_signature"] == b"\x89PNG\r\n\x1a\n"
