from __future__ import annotations

import hashlib
import io
import uuid
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.providers.kie_prompt_tools import KiePromptToolsClient, PromptToolProviderResult
from app.services.photo_analysis_media import image_source_to_analysis_input
from app.services.prompt_tools import PromptToolService
from app.services.reference_static import ReferenceStaticStorage


def _persist_png(monkeypatch: pytest.MonkeyPatch, tmp_path) -> str:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "refs"))
    raw = io.BytesIO()
    Image.new("RGBA", (3200, 1200), (255, 0, 0, 128)).save(raw, format="PNG")
    data = raw.getvalue()
    stream = io.BytesIO(data)
    url, _path, _size = ReferenceStaticStorage.persist_stream(
        stream,
        user_id=uuid.uuid4(),
        kind="image",
        file_hash=hashlib.sha256(data).hexdigest(),
        filename="photo.png",
        content_type="image/png",
        expected_size=len(data),
    )
    return url


def test_photo_analysis_converts_durable_reference_to_bounded_jpeg_data_uri(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    url = _persist_png(monkeypatch, tmp_path)
    prepared = image_source_to_analysis_input(url)
    assert prepared is not None
    assert prepared.startswith("data:image/jpeg;base64,")
    assert url not in prepared


def test_prompt_tool_accepts_roxy_owned_photo_reference(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    url = _persist_png(monkeypatch, tmp_path)
    clean = PromptToolService._normalize_input(
        "prompt_builder",
        {"text": "Сделай такой же свет", "image_url": url},
    )
    # Durable URL remains the task source of truth; conversion is JIT in the provider adapter.
    assert clean["image_url"] == url


@pytest.mark.asyncio
async def test_image_prompt_uses_tanyapi_chain_and_never_sends_local_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    url = _persist_png(monkeypatch, tmp_path)
    provider = AsyncMock(
        return_value=PromptToolProviderResult(
            model="gpt-5-4",
            payload={"prompt_ru": "RU", "prompt_en": "EN"},
        )
    )
    monkeypatch.setattr("app.services.tanyapi_prompt_contract.build_photo_prompt", provider)

    client = KiePromptToolsClient("test-key", "https://api.kie.ai")
    try:
        result = await client.build_prompt(text="сохрани композицию", image_url=url)
    finally:
        await client.aclose()

    assert result.model == "gpt-5-4"
    kwargs = provider.await_args.kwargs
    assert kwargs["instruction"] == "сохрани композицию"
    assert kwargs["image_url"].startswith("data:image/jpeg;base64,")
    assert url not in kwargs["image_url"]
