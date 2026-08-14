from pathlib import Path

from app.api.v1.prompt_tools import (
    ImageAnalysisRequest,
    PromptBuilderRequest,
    _prompt_builder_payload,
)
from app.providers.kie_prompt_tools import _parse_json_object, _responses_output_text

ROOT = Path(__file__).resolve().parents[1]


def test_public_requests_cannot_select_model_or_price() -> None:
    assert set(ImageAnalysisRequest.model_fields) == {"image_url", "instruction"}
    assert set(PromptBuilderRequest.model_fields) == {"text", "image_url", "purpose"}
    for schema in (ImageAnalysisRequest.model_fields, PromptBuilderRequest.model_fields):
        assert "model" not in schema
        assert "cost" not in schema
        assert "provider" not in schema


def test_prompt_builder_purpose_is_bounded_server_owned_context() -> None:
    video = PromptBuilderRequest(text="Девушка идёт по Токио", purpose="video")
    video_payload = _prompt_builder_payload(video)
    assert "генерации видео" in str(video_payload["text"])
    assert "движение камеры" in str(video_payload["text"])
    assert "Идея пользователя: Девушка идёт по Токио" in str(video_payload["text"])

    image = PromptBuilderRequest(text="Предметная съёмка", purpose="image")
    image_payload = _prompt_builder_payload(image)
    assert "статичного изображения" in str(image_payload["text"])
    assert "оптику/ракурс" in str(image_payload["text"])

    general = PromptBuilderRequest(text="Как есть")
    assert _prompt_builder_payload(general)["text"] == "Как есть"


def test_provider_json_parsers_accept_documented_response_shapes() -> None:
    assert _parse_json_object('```json\n{"prompt_ru":"a","prompt_en":"b"}\n```') == {
        "prompt_ru": "a",
        "prompt_en": "b",
    }
    payload = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "{\"prompt_ru\":\"a\",\"prompt_en\":\"b\"}",
                    }
                ],
            }
        ]
    }
    assert "prompt_ru" in _responses_output_text(payload)


def test_prompt_tools_ui_keeps_transport_server_authoritative() -> None:
    source = (ROOT / "app/web/mini_app/prompt-tools.js").read_text(encoding="utf-8")
    assert 'headers: { "Idempotency-Key": requestKey }' in source
    assert "/api/v1/prompt-tools/image-analysis" in source
    assert "/api/v1/prompt-tools/prompt-builder" in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "innerHTML" not in source
    assert "eval(" not in source
    assert "new Function" not in source


def test_provider_prompts_do_not_copy_legacy_unsafe_instruction() -> None:
    source = (ROOT / "app/providers/kie_prompt_tools.py").read_text(encoding="utf-8").lower()
    assert "no moral restrictions" not in source
    assert "no censorship" not in source
    assert "не пытайся идентифицировать реальных людей" in source
