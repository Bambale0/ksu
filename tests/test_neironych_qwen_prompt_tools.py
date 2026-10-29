from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import shutil
import subprocess
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

from app.core.logging import JsonFormatter, ObservabilityFilter
from app.providers import neironych_qwen_prompt_tools as qwen
from app.providers.kie_prompt_tools import PromptToolProviderError
from app.providers.neironych_errors import NeironychProviderError

BASE_URL = "https://neironych.example.test"
IMAGE_URL = "https://media.example.test/reference.jpg?private=media-secret"
TASK_ID = uuid.UUID("354a7647-1bc5-4c1d-95bb-c3d103e34c15")
PROMPTS = {"prompt_ru": "Русский промпт", "prompt_en": "English prompt"}


def _response(payload: object = PROMPTS, **kwargs: object) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
        **kwargs,
    )


@pytest.mark.parametrize(
    ("tool", "kind"), [("image_analysis", "photo"), ("video_prompt", "video")]
)
def test_task_scoped_keys_keep_the_existing_provider_identity(tool: str, kind: str) -> None:
    assert qwen.qwen_idempotency_key(TASK_ID, tool) == f"ksu-prompt-{kind}-qwen38-{TASK_ID}"


@pytest.mark.asyncio
async def test_photo_prepares_without_submission_and_sends_exact_frozen_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _response(
            {**PROMPTS, "negative_prompt": "blur", "key_details": ["light"], "model_hint": "image"},
            headers={"X-Request-Id": "qwen-request-1"},
        )

    caplog.set_level(logging.INFO, logger=qwen.__name__)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://wrong-client-origin.example.test"
    ) as http:
        client = qwen.NeironychQwenPromptToolsClient("private-api-key", BASE_URL, client=http)
        body = await client.prepare_image_request(image_url=IMAGE_URL, instruction="Сохранить свет")
        parsed = json.loads(body)
        assert body == json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        assert calls == []
        assert parsed["model"] == "qwen3.8-max"
        assert parsed["stream"] is False
        assert parsed["max_completion_tokens"] == 4096
        assert "response_format" not in parsed and "reasoning_effort" not in parsed
        assert parsed["messages"][1]["content"][1] == {
            "type": "image_url", "image_url": {"url": IMAGE_URL}
        }
        assert "Сохранить свет" in parsed["messages"][1]["content"][0]["text"]
        # The service owns integrity. The adapter must not reserialize even
        # semantically identical saved JSON during an explicit replay.
        frozen = json.dumps(parsed, ensure_ascii=False, indent=2)
        for _ in range(2):
            result = await client.submit(
                request_body=frozen, task_id=TASK_ID, tool="image_analysis", model=qwen.QWEN_MODEL
            )
            assert result.model == qwen.QWEN_MODEL
            assert result.payload["prompt_ru"] == PROMPTS["prompt_ru"]
            assert result.payload["negative_prompt"] == "blur"
            assert result.payload["key_details"] == ["light"]
        await client.aclose()
        assert not http.is_closed

    assert len(calls) == 2
    for request in calls:
        assert str(request.url) == BASE_URL + "/v1/chat/completions"
        assert request.method == "POST"
        assert request.content == frozen.encode("utf-8")
        assert request.headers["Authorization"] == "Bearer private-api-key"
        assert request.headers["Idempotency-Key"] == f"ksu-prompt-photo-qwen38-{TASK_ID}"
        assert request.headers["X-Client-Request-Id"] == str(TASK_ID)
        assert request.headers["X-Submission-Receipt"] == "v1"
        assert request.headers["Accept-Encoding"] == "identity"
        assert all(0 < value <= 120 for value in request.extensions["timeout"].values())
    events = [record for record in caplog.records if record.name == qwen.__name__]
    assert len(events) == 2
    for record in events:
        # Production ignores arbitrary logging extras and replaces request_id
        # with KSU correlation context. Supplier identity must survive both.
        ObservabilityFilter().filter(record)
        event = json.loads(JsonFormatter().format(record))
        assert "provider_request_id=qwen-request-1" in event["message"]
        assert f"task_id={TASK_ID}" in event["message"]
        assert event["http_status"] == 200 and event["duration_ms"] >= 0
    assert "private-api-key" not in caplog.text and "media-secret" not in caplog.text
    assert PROMPTS["prompt_en"] not in caplog.text


@pytest.mark.asyncio
@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg/ffprobe required"
)
async def test_video_preparation_samples_real_bytes_in_chronological_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    video = tmp_path / "four-colors.mp4"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for color in ("red", "lime", "blue", "white"):
        command.extend(["-f", "lavfi", "-i", f"color=c={color}:s=32x24:r=4:d=1"])
    command.extend([
        "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[out]",
        "-map", "[out]", "-an", "-c:v", "mpeg4", "-q:v", "2", "-threads", "1", str(video),
    ])
    subprocess.run(command, check=True, capture_output=True, timeout=20)
    download = AsyncMock(return_value=video.read_bytes())
    monkeypatch.setattr(qwen, "_video_bytes", download)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _response({
            **PROMPTS, "camera_movement_ru": "Статичная камера", "timeline_ru": ["Первый", "Второй"],
            "visual_style_ru": "Яркие цвета", "audio_notes_ru": "Слышны музыка и шум моря",
            "key_details": ["цвет"],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = qwen.NeironychQwenPromptToolsClient("test-key", BASE_URL, client=http)
        body = await client.prepare_video_request(
            video_url="https://media.example.test/clip.mp4", instruction="Цвета", duration_seconds=15,
        )
        assert calls == []
        parsed = json.loads(body)
        assert parsed["max_completion_tokens"] == 8192
        content = parsed["messages"][1]["content"]
        assert "Measured source duration: 4 seconds" in content[0]["text"]
        assert "Requested target duration: 15 seconds" in content[0]["text"]
        assert "chronological" in content[0]["text"]
        assert "Do not invent audio" in content[0]["text"]
        assert len(content) == 5
        colors = []
        for item in content[1:]:
            assert item["type"] == "image_url"
            prefix, encoded = item["image_url"]["url"].split(",", 1)
            assert prefix == "data:image/jpeg;base64"
            raw = base64.b64decode(encoded, validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                assert image.format == "JPEG"
                colors.append(image.convert("RGB").getpixel((8, 8)))
        assert colors[0][0] > max(colors[0][1:]) + 100
        assert colors[1][1] > max(colors[1][0], colors[1][2]) + 100
        assert colors[2][2] > max(colors[2][:2]) + 100
        assert min(colors[3]) > 200
        assert "video_url" not in body and "input_video" not in body
        result = await client.submit(
            request_body=body, task_id=TASK_ID, tool="video_prompt", model=qwen.QWEN_MODEL,
        )
    assert len(calls) == 1
    assert calls[0].headers["Idempotency-Key"] == f"ksu-prompt-video-qwen38-{TASK_ID}"
    assert result.payload["camera_movement_ru"] == "Статичная камера"
    assert result.payload["timeline_ru"] == ["Первый", "Второй"]
    assert result.payload["audio_notes_ru"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [None, True, 123, ["prompt"], {"text": "prompt"}, "", "   "])
@pytest.mark.parametrize("field", ["prompt_ru", "prompt_en"])
async def test_invalid_prompt_fields_are_terminal_and_never_reposted(field: str, bad: object) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _response({**PROMPTS, field: bad}, headers={"X-Request-Id": "invalid-output-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = qwen.NeironychQwenPromptToolsClient("test-key", BASE_URL, client=http)
        body = await client.prepare_image_request(image_url=IMAGE_URL)
        with pytest.raises(NeironychProviderError) as caught:
            await client.submit(request_body=body, task_id=TASK_ID, tool="image_analysis", model=qwen.QWEN_MODEL)
    assert len(calls) == 1
    assert caught.value.error_code == "prompt_response_invalid"
    assert caught.value.status_code == 200
    assert caught.value.request_id == "invalid-output-1"
    assert caught.value.payload is None
    assert not caught.value.local_validation


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [b"private invalid JSON", b'{}', b'{"choices":[]}', b'{"error":{"message":"private"}}'])
async def test_invalid_success_envelope_does_not_retry_or_expose_content(content: bytes) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=content)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = qwen.NeironychQwenPromptToolsClient("test-key", BASE_URL, client=http)
        body = await client.prepare_image_request(image_url=IMAGE_URL)
        with pytest.raises(NeironychProviderError) as caught:
            await client.submit(request_body=body, task_id=TASK_ID, tool="image_analysis", model=qwen.QWEN_MODEL)
    assert len(calls) == 1 and caught.value.error_code == "prompt_response_invalid"
    assert "private" not in str(caught.value) and caught.value.payload is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "code"), [
    (401, "invalid_api_key"), (402, "insufficient_balance"), (409, "request_already_submitted"),
    (410, "idempotent_result_expired"), (422, "invalid_request_contract"),
    (429, "provider_rate_limited"), (503, "provider_temporarily_unavailable"),
])
async def test_http_errors_preserve_safe_contract_fields_without_retries(status: int, code: str) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status,
            json={"error": {"code": code, "message": "private-api-key media-secret"}},
            headers={"X-Request-Id": "provider-request-1", "Retry-After": "7"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = qwen.NeironychQwenPromptToolsClient("test-key", BASE_URL, client=http)
        body = await client.prepare_image_request(image_url=IMAGE_URL)
        with pytest.raises(NeironychProviderError) as caught:
            await client.submit(request_body=body, task_id=TASK_ID, tool="image_analysis", model=qwen.QWEN_MODEL)
    error = caught.value
    assert len(calls) == 1
    assert (error.status_code, error.error_code, error.request_id, error.retry_after) == (
        status, code, "provider-request-1", 7,
    )
    assert error.payload is None and not error.local_validation and not error.submission_rejected
    assert "private-api-key" not in str(error) and "media-secret" not in str(error)
    assert error.__cause__ is None


@pytest.mark.asyncio
@pytest.mark.parametrize("receipt", ["valid", "wrong-client", "wrong-key", "extra-body", "absent"])
async def test_only_bound_rejection_receipt_marks_submission_rejected(receipt: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {
            "X-Submission-State": "not-accepted-v1",
            "X-Client-Request-Id": str(TASK_ID),
            "X-Idempotency-Key-Sha256": hashlib.sha256(request.headers["Idempotency-Key"].encode()).hexdigest(),
        }
        payload = {"detail": "provider_temporarily_unavailable"}
        if receipt == "wrong-client":
            headers["X-Client-Request-Id"] = str(uuid.uuid4())
        elif receipt == "wrong-key":
            headers["X-Idempotency-Key-Sha256"] = "0" * 64
        elif receipt == "extra-body":
            payload["private"] = "hidden"
        elif receipt == "absent":
            headers = {}
        return httpx.Response(503, headers=headers, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = qwen.NeironychQwenPromptToolsClient("test-key", BASE_URL, client=http)
        body = await client.prepare_image_request(image_url=IMAGE_URL)
        with pytest.raises(NeironychProviderError) as caught:
            await client.submit(request_body=body, task_id=TASK_ID, tool="image_analysis", model=qwen.QWEN_MODEL)
    assert caught.value.submission_rejected is (receipt == "valid")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "disconnect", "total-deadline"])
async def test_transport_and_total_deadline_remain_unknown_without_an_internal_retry(
    failure: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if failure == "total-deadline":
            await asyncio.sleep(1)
            return _response()
        error = httpx.ReadTimeout if failure == "timeout" else httpx.RemoteProtocolError
        raise error("private-api-key media-secret", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = qwen.NeironychQwenPromptToolsClient("test-key", BASE_URL, client=http)
        body = await client.prepare_image_request(image_url=IMAGE_URL)
        monkeypatch.setattr(qwen, "QWEN_TOTAL_TIMEOUT_SECONDS", 0.01)
        with pytest.raises(NeironychProviderError) as caught:
            await client.submit(request_body=body, task_id=TASK_ID, tool="image_analysis", model=qwen.QWEN_MODEL)
    assert len(calls) == 1 and caught.value.error_code == "submission_outcome_unknown"
    assert not caught.value.local_validation and not caught.value.submission_rejected
    assert "private" not in str(caught.value) and "media-secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_redirects_are_not_followed_even_with_an_injected_redirecting_client() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://untrusted.example.test/steal"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as http:
        client = qwen.NeironychQwenPromptToolsClient("test-key", BASE_URL, client=http)
        body = await client.prepare_image_request(image_url=IMAGE_URL)
        with pytest.raises(NeironychProviderError) as caught:
            await client.submit(request_body=body, task_id=TASK_ID, tool="image_analysis", model=qwen.QWEN_MODEL)
    assert len(calls) == 1 and caught.value.status_code == 307


@pytest.mark.asyncio
async def test_streamed_success_response_is_capped_before_json_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    consumed = []

    class LargeResponse(httpx.AsyncByteStream):
        async def __aiter__(self):
            for number in range(20):
                consumed.append(number)
                yield b"private-response" * 1024

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=LargeResponse(), headers={"X-Request-Id": "large-response-1"})

    monkeypatch.setattr(qwen, "QWEN_MAX_RESPONSE_BYTES", 32 * 1024)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = qwen.NeironychQwenPromptToolsClient("test-key", BASE_URL, client=http)
        body = await client.prepare_image_request(image_url=IMAGE_URL)
        with pytest.raises(NeironychProviderError) as caught:
            await client.submit(request_body=body, task_id=TASK_ID, tool="image_analysis", model=qwen.QWEN_MODEL)
    assert len(consumed) < 20
    assert caught.value.error_code == "prompt_response_invalid"
    assert caught.value.request_id == "large-response-1" and caught.value.payload is None


@pytest.mark.asyncio
async def test_unexpected_compressed_response_is_rejected_before_decompression() -> None:
    consumed = []

    class CompressedResponse(httpx.AsyncByteStream):
        async def __aiter__(self):
            consumed.append(True)
            yield b"untrusted compressed bytes"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=CompressedResponse())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = qwen.NeironychQwenPromptToolsClient("test-key", BASE_URL, client=http)
        body = await client.prepare_image_request(image_url=IMAGE_URL)
        with pytest.raises(NeironychProviderError) as caught:
            await client.submit(request_body=body, task_id=TASK_ID, tool="image_analysis", model=qwen.QWEN_MODEL)
    assert consumed == [] and caught.value.error_code == "prompt_response_invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize("body_kind", ["compressed", "oversize", "unreadable"])
async def test_expired_replay_remains_terminal_without_reading_its_body(body_kind: str) -> None:
    consumed = []
    calls = []

    class UnreadableResponse(httpx.AsyncByteStream):
        async def __aiter__(self):
            consumed.append(True)
            raise httpx.ReadError("private response failure")
            yield b""  # Make this an async generator without reading any real data.

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        headers = {"X-Request-Id": "expired-request-1", "Retry-After": "7"}
        if body_kind == "compressed":
            headers["Content-Encoding"] = "gzip"
        elif body_kind == "oversize":
            headers["Content-Length"] = str(qwen.QWEN_MAX_RESPONSE_BYTES + 1)
        return httpx.Response(410, headers=headers, stream=UnreadableResponse())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = qwen.NeironychQwenPromptToolsClient("test-key", BASE_URL, client=http)
        body = await client.prepare_image_request(image_url=IMAGE_URL)
        with pytest.raises(NeironychProviderError) as caught:
            await client.submit(request_body=body, task_id=TASK_ID, tool="image_analysis", model=qwen.QWEN_MODEL)
    assert len(calls) == 1 and consumed == []
    assert caught.value.error_code == "idempotent_result_expired"
    assert caught.value.status_code == 410 and caught.value.request_id == "expired-request-1"
    assert caught.value.retry_after == 7 and caught.value.payload is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["model", "tool", "uuid", "native-video", "stream", "tokens", "oversize", "duplicate-model"])
async def test_invalid_frozen_request_identity_is_rejected_before_post(
    change: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = qwen.NeironychQwenPromptToolsClient("test-key", BASE_URL, client=http)
        body = await client.prepare_image_request(image_url=IMAGE_URL)
        parsed = json.loads(body)
        tool = "image_analysis"
        task_id: object = TASK_ID
        if change == "model":
            parsed["model"] = "other-model"
        elif change == "tool":
            tool = "video_prompt"
        elif change == "uuid":
            task_id = "private-invalid-task"
        elif change == "native-video":
            parsed["messages"][1]["content"][1] = {"type": "video_url", "video_url": {"url": IMAGE_URL}}
        elif change == "stream":
            parsed["stream"] = True
        elif change == "tokens":
            parsed["max_completion_tokens"] = 8192
        elif change == "oversize":
            monkeypatch.setattr(qwen, "QWEN_MAX_REQUEST_BYTES", 64)
        body = json.dumps(parsed)
        if change == "duplicate-model":
            body = body.replace('"model":', '"model":"other-model","model":', 1)
        with pytest.raises(NeironychProviderError) as caught:
            await client.submit(request_body=body, task_id=task_id, tool=tool, model=qwen.QWEN_MODEL)
    assert calls == []
    assert caught.value.local_validation and caught.value.payload is None


@pytest.mark.asyncio
async def test_media_preparation_failure_is_sanitized_and_cannot_submit(monkeypatch: pytest.MonkeyPatch) -> None:
    download = AsyncMock(side_effect=PromptToolProviderError("private-path media-secret"))
    monkeypatch.setattr(qwen, "_video_bytes", download)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: _response())) as http:
        client = qwen.NeironychQwenPromptToolsClient("test-key", BASE_URL, client=http)
        with pytest.raises(NeironychProviderError) as caught:
            await client.prepare_video_request(video_url="https://media.example.test/private.mp4")
    assert caught.value.local_validation and caught.value.error_code == "invalid_request_contract"
    assert "private" not in str(caught.value) and caught.value.payload is None


@pytest.mark.asyncio
@pytest.mark.parametrize("image_url", ["http://example.test/a.jpg", "https://user:secret@example.test/a.jpg", "https://127.0.0.1/a.jpg", "https://localhost/a.jpg", "data:image/jpeg;base64,AA=="])
async def test_unsafe_photo_sources_are_rejected_before_post(image_url: str) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: _response())) as http:
        client = qwen.NeironychQwenPromptToolsClient("test-key", BASE_URL, client=http)
        with pytest.raises(NeironychProviderError) as caught:
            await client.prepare_image_request(image_url=image_url)
    assert caught.value.local_validation


@pytest.mark.parametrize("origin", ["http://example.test", "https://user:secret@example.test", "https://example.test/v1", "https://example.test?secret=x"])
def test_provider_origin_must_be_an_unauthenticated_https_origin(origin: str) -> None:
    with pytest.raises(NeironychProviderError) as caught:
        qwen.NeironychQwenPromptToolsClient("test-key", origin)
    assert caught.value.local_validation and "secret" not in str(caught.value)
