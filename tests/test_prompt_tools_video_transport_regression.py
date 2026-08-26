from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import settings
from app.services.provider_media_transport import ProviderMediaTransport


@pytest.mark.asyncio
async def test_absolute_roxy_video_is_recovered_when_worker_has_no_local_copy(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "refs"))
    monkeypatch.setenv("REFERENCE_STATIC_PUBLIC_PREFIX", "/uploads/refs")
    monkeypatch.setattr(settings, "public_base_url", "https://api.roxy.test")
    monkeypatch.setattr(settings, "kie_api_key", "test-key")
    monkeypatch.setattr(settings, "kie_upload_max_bytes", 10 * 1024 * 1024)

    video = b"roxy-video-bytes"
    stable_url = "https://api.roxy.test/uploads/refs/video/user/2026/08/source.mp4"
    recovered_requests: list[str] = []
    uploaded: dict[str, object] = {}

    def recover(request: httpx.Request) -> httpx.Response:
        recovered_requests.append(str(request.url))
        assert request.method == "GET"
        return httpx.Response(
            200,
            headers={"content-type": "video/mp4", "content-length": str(len(video))},
            content=video,
        )

    monkeypatch.setattr(
        ProviderMediaTransport,
        "_recovery_client",
        staticmethod(
            lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(recover),
                follow_redirects=False,
            )
        ),
    )

    class FakeKieClient:
        def __init__(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            pass

        async def upload_stream(self, *, file_name, content_type, stream, upload_path):  # type: ignore[no-untyped-def]
            uploaded.update(
                file_name=file_name,
                content_type=content_type,
                payload=stream.read(),
                upload_path=upload_path,
            )
            return SimpleNamespace(url="https://kie.example/runtime/source.mp4")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        "app.services.provider_media_transport.KieUploadClient",
        FakeKieClient,
    )

    local_path = ProviderMediaTransport._local_path(stable_url)
    assert local_path is not None
    assert not local_path.exists()

    prepared = await ProviderMediaTransport.prepare({"video_url": stable_url})

    assert recovered_requests == [stable_url]
    assert prepared["video_url"] == "https://kie.example/runtime/source.mp4"
    assert uploaded["payload"] == video
    assert uploaded["content_type"] == "video/mp4"
    assert uploaded["upload_path"] == "ksu/runtime-inputs"


def test_prompt_tools_mobile_error_contract_prevents_horizontal_overflow() -> None:
    root = Path(__file__).resolve().parents[1] / "frontend/mini-app"
    styles = (root / "app/standalone-tools.css").read_text(encoding="utf-8")
    page = (root / "app/prompt-tools/page.tsx").read_text(encoding="utf-8")

    assert ".tool-panel>*{min-width:0;max-width:100%}" in styles
    assert ".action-error{min-width:0;max-width:100%;overflow-wrap:anywhere" in styles
    assert ".primary.wide{min-width:0;max-width:100%;white-space:normal}" in styles
    assert "function promptToolError" in page
    assert "Не удалось обработать файл. Загрузите его ещё раз и повторите." in page
