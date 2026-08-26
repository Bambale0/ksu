from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from app.providers.kie_prompt_tools import PromptToolProviderError, PromptToolProviderResult
from app.providers.tanyapi_photo_prompt import GPT_MAX_ATTEMPTS, _application_error, _extract_output_text

VIDEO_MODEL = "gpt-5-5"
VIDEO_PROMPT_FRAME_COUNT = 6
VIDEO_PROMPT_FRAME_TIMEOUT_SECONDS = 60
VIDEO_PROMPT_MAX_VIDEO_BYTES = 30 * 1024 * 1024
VIDEO_PROMPT_MAX_DURATION_SECONDS = 60
_RETRYABLE_BODY_CODES = {429}

VIDEO_SYSTEM_PROMPT = """
You are a senior prompt analyst for photorealistic AI video generation.

Your task:
Analyze the attached reference video file and create a polished prompt for generating a visually similar video. Focus on what a video generation model needs: subject/action, shot size, camera movement, temporal rhythm, scene transitions, environment, lighting, color, motion physics, visual style, and mood.

Primary output style:
- The user-facing "prompt_ru" is the main result. Write it in Russian as one natural, dense cinematic/video prompt, similar to a fashion/editorial reference description but adapted for motion.
- Use one cohesive paragraph, not a bullet list and not a technical checklist.
- Target length for "prompt_ru": 1100-2200 characters when the video has enough detail.
- Follow this rhythm when applicable: opening frame and shot size, subject/objects and visible appearance, action over time, pose/gaze/gestures, camera path and lens feel, pacing and timing, environment/background, lighting changes, color palette, depth of field/focus behavior, atmosphere, final frame.
- Preserve the motion language: handheld/static, dolly, push-in, pull-out, orbit, pan, tilt, tracking, slow motion, speed ramp, natural body/object movement, reflections, occlusion, foreground/background separation.
- Do not add generic filler such as "8k", "masterpiece", "ultra detailed", "best quality" unless the visible style clearly calls for a short quality phrase.
- Do not use forensic, pixel-by-pixel, biometric, identity-preservation, medical, or anatomical jargon.

Prompt fields:
- "prompt_ru": polished Russian video generation prompt in the style above.
- "prompt_en": faithful English version optimized for video generation models, also one cohesive paragraph.
- "negative_prompt": concise English list of video defects to avoid.
- "camera_movement_ru": short Russian summary of camera movement and framing.
- "timeline_ru": 3-6 short Russian beats that describe the clip over time.
- "visual_style_ru": short Russian summary of style, light, color and mood.
- "audio_notes_ru": short Russian note about audible elements if they matter, or empty string.
- "model_hint": short Russian recommendation of the best model/workflow.
- "key_details": 4-8 short visible/motion details that most affect similarity.

Strict safety rules:
- Do not identify any person.
- Do not guess names, ethnicity, nationality, private attributes, or exact age.
- You may use broad visible age presentation only if visually obvious, such as "young adult" / "молодой взрослый человек"; never provide a number.
- Describe only visible visual features, motion, environment, style and user-provided creative instructions.
- Return only valid JSON. No markdown. No explanation.

JSON schema:
{
  "prompt_en": "Detailed English video generation prompt",
  "prompt_ru": "Natural Russian cinematic video prompt for the user",
  "negative_prompt": "Common video defects to avoid",
  "camera_movement_ru": "Camera movement and framing summary",
  "timeline_ru": ["beat 1", "beat 2", "beat 3"],
  "visual_style_ru": "Style, lighting, color and mood summary",
  "audio_notes_ru": "Audio note, or empty string",
  "model_hint": "Short Russian recommendation which model to use",
  "key_details": ["detail 1", "detail 2", "detail 3", "detail 4"]
}
""".strip()

_DEFAULT_NEGATIVE = (
    "blurry, low quality, flicker, jitter, warped motion, distorted face, bad anatomy, "
    "bad hands, temporal inconsistency, duplicated objects, watermark, text, logo, "
    "overexposed, underexposed"
)
_DEFAULT_HINT = (
    "Gemini Omni Video — для работы с видео-референсом. Seedance 2.0 — "
    "для похожего движения/камеры. Grok Imagine 1.5 — для коротких I2V-сцен."
)


def _parse_video_json_object(raw_text: str) -> dict[str, Any]:
    text = str(raw_text or "").strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    return {
        "prompt_en": text,
        "prompt_ru": "Не удалось разобрать структурированный ответ. Используйте английский prompt выше.",
        "negative_prompt": _DEFAULT_NEGATIVE,
        "camera_movement_ru": "",
        "timeline_ru": [],
        "visual_style_ru": "",
        "audio_notes_ru": "",
        "model_hint": _DEFAULT_HINT,
        "key_details": [],
    }


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _result(parsed: dict[str, Any], *, model: str) -> PromptToolProviderResult:
    prompt_en = str(parsed.get("prompt_en") or "").strip()
    prompt_ru = str(parsed.get("prompt_ru") or "").strip()
    if not prompt_ru and not prompt_en:
        raise PromptToolProviderError("video prompt is empty")
    if not prompt_ru:
        prompt_ru = "Используйте английский prompt ниже как основу для генерации похожего видео."
    if not prompt_en:
        prompt_en = prompt_ru

    payload: dict[str, Any] = {
        "prompt_en": prompt_en,
        "prompt_ru": prompt_ru,
        "negative_prompt": str(parsed.get("negative_prompt") or _DEFAULT_NEGATIVE).strip(),
        "camera_movement_ru": str(parsed.get("camera_movement_ru") or "").strip(),
        "timeline_ru": _as_string_list(parsed.get("timeline_ru")),
        "visual_style_ru": str(parsed.get("visual_style_ru") or "").strip(),
        "audio_notes_ru": str(parsed.get("audio_notes_ru") or "").strip(),
        "model_hint": str(parsed.get("model_hint") or _DEFAULT_HINT).strip(),
        "key_details": _as_string_list(parsed.get("key_details")),
        "provider": model,
    }
    return PromptToolProviderResult(model=model, payload=payload, credits_consumed=None)


def _native_content(*, user_instruction: str, video_url: str, filename: str) -> list[dict[str, Any]]:
    return [
        {"type": "input_text", "text": user_instruction},
        {
            "type": "input_file",
            "file_url": video_url,
            "filename": filename or "reference_video.mp4",
        },
    ]


def _frame_content(*, user_instruction: str, frame_data_urls: list[str]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "input_text", "text": user_instruction}]
    for frame_url in frame_data_urls:
        content.append({"type": "input_image", "image_url": frame_url})
    return content


def _extract_frame_data_urls_sync(
    video_bytes: bytes,
    *,
    duration_seconds: int | float = 0,
    max_frames: int = VIDEO_PROMPT_FRAME_COUNT,
) -> list[str]:
    if not video_bytes:
        raise PromptToolProviderError("video bytes are required for frame fallback")

    max_frames = max(1, int(max_frames or VIDEO_PROMPT_FRAME_COUNT))
    duration = float(duration_seconds or 0)
    fps = max_frames / duration if duration > 0 else 1.0
    fps = max(0.05, min(2.0, fps))

    with tempfile.TemporaryDirectory(prefix="video_prompt_") as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / "input_video"
        input_path.write_bytes(video_bytes)
        output_pattern = str(temp_path / "frame_%03d.jpg")
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-vf",
            f"fps={fps:.4f},scale=768:-2:force_original_aspect_ratio=decrease",
            "-frames:v",
            str(max_frames),
            "-q:v",
            "5",
            output_pattern,
        ]
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=VIDEO_PROMPT_FRAME_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise PromptToolProviderError("Не удалось извлечь кадры из видео: timeout") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            raise PromptToolProviderError(
                f"Не удалось извлечь кадры из видео: {stderr[:300]}"
            ) from exc

        frames: list[str] = []
        for frame_path in sorted(temp_path.glob("frame_*.jpg"))[:max_frames]:
            encoded = base64.b64encode(frame_path.read_bytes()).decode("ascii")
            frames.append(f"data:image/jpeg;base64,{encoded}")

    if not frames:
        raise PromptToolProviderError("Не удалось извлечь кадры из видео")
    return frames


async def _post_responses(
    client: httpx.AsyncClient,
    *,
    body: dict[str, Any],
    model_label: str,
    max_attempts: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    max_attempts = max(1, int(max_attempts))
    for attempt in range(max_attempts):
        try:
            response = await client.post("/codex/v1/responses", json=body, timeout=180.0)
            if response.status_code == 429 or response.status_code >= 500:
                raise PromptToolProviderError(
                    f"{model_label} temporary HTTP {response.status_code}"
                )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Provider response must be an object")
            if _application_error(data):
                raise PromptToolProviderError(f"{model_label} upstream application error")
            try:
                body_code = int(data.get("code") or 0)
            except (TypeError, ValueError):
                body_code = 0
            if body_code >= 400:
                retryable = body_code in _RETRYABLE_BODY_CODES
                message = "temporary" if retryable else "application"
                raise PromptToolProviderError(f"{model_label} {message} error {body_code}")
            return data
        except (httpx.HTTPError, ValueError, PromptToolProviderError) as exc:
            last_error = exc
            message = str(exc).lower()
            retryable = (
                isinstance(exc, httpx.HTTPError)
                or "temporary" in message
                or "upstream" in message
            )
            if attempt < max_attempts - 1 and retryable:
                await asyncio.sleep(2**attempt)
                continue
            break
    raise PromptToolProviderError(f"{model_label} video prompt failed: {last_error}") from last_error


async def _analyze_native(
    client: httpx.AsyncClient,
    *,
    video_url: str,
    filename: str,
    user_instruction: str,
) -> PromptToolProviderResult:
    body = {
        "model": VIDEO_MODEL,
        "stream": False,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": VIDEO_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": _native_content(
                    user_instruction=user_instruction,
                    video_url=video_url,
                    filename=filename,
                ),
            },
        ],
        "reasoning": {"effort": "high"},
    }
    # tanyapi deliberately tries native file input once and switches quickly to frames.
    data = await _post_responses(
        client,
        body=body,
        model_label=VIDEO_MODEL,
        max_attempts=1,
    )
    return _result(_parse_video_json_object(_extract_output_text(data)), model=VIDEO_MODEL)


async def _analyze_frames(
    client: httpx.AsyncClient,
    *,
    frame_data_urls: list[str],
    user_instruction: str,
) -> PromptToolProviderResult:
    frame_instruction = (
        user_instruction
        + "\n\nNative video-file input was unavailable, so the attached images are "
        "representative frames sampled from the source video in chronological order. "
        "Analyze them as a temporal sequence and infer camera movement, motion rhythm and "
        "transitions from frame-to-frame differences. Be honest about visible information "
        "and do not invent unavailable audio."
    )
    body = {
        "model": VIDEO_MODEL,
        "stream": False,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": VIDEO_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": _frame_content(
                    user_instruction=frame_instruction,
                    frame_data_urls=frame_data_urls,
                ),
            },
        ],
        "reasoning": {"effort": "high"},
    }
    data = await _post_responses(
        client,
        body=body,
        model_label=f"{VIDEO_MODEL}-frames",
        max_attempts=GPT_MAX_ATTEMPTS,
    )
    return _result(
        _parse_video_json_object(_extract_output_text(data)),
        model=f"{VIDEO_MODEL}-frames",
    )


async def _download_video_bytes(client: httpx.AsyncClient, video_url: str) -> bytes:
    try:
        response = await client.get(video_url, timeout=90.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PromptToolProviderError(f"Не удалось скачать видео для fallback: {exc}") from exc

    try:
        content_length = int(response.headers.get("Content-Length") or 0)
    except (TypeError, ValueError):
        content_length = 0
    if content_length and content_length > VIDEO_PROMPT_MAX_VIDEO_BYTES:
        raise PromptToolProviderError("Видео слишком большое для frame fallback")
    data = response.content
    if len(data) > VIDEO_PROMPT_MAX_VIDEO_BYTES:
        raise PromptToolProviderError("Видео слишком большое для frame fallback")
    return data


async def build_video_prompt(
    client: httpx.AsyncClient,
    *,
    video_url: str,
    instruction: str = "",
    duration_seconds: int | float = 0,
    filename: str = "reference_video.mp4",
    video_bytes: bytes | None = None,
) -> PromptToolProviderResult:
    """Port tanyapi's native-video -> sampled-frames prompt analysis chain."""

    video_url = str(video_url or "").strip()
    if not video_url:
        raise PromptToolProviderError("video_url is required")
    duration = float(duration_seconds or 0)
    if duration < 0 or duration > VIDEO_PROMPT_MAX_DURATION_SECONDS:
        raise PromptToolProviderError(
            f"Видео должно быть не длиннее {VIDEO_PROMPT_MAX_DURATION_SECONDS} секунд"
        )

    extras: list[str] = []
    if instruction.strip():
        extras.append(f"Additional text instruction from user:\n{instruction.strip()}")
    if duration:
        extras.append(f"Telegram-reported clip duration: {duration:g} seconds.")
    extra_instruction = "\n\n".join(extras)

    user_instruction = (
        "Analyze this attached reference video file and create a detailed prompt for "
        "generating a visually similar video.\n\n"
        "User goal:\nGenerate a similar video that preserves the visible subject, "
        "action, camera movement, pacing, lighting, color, environment and mood.\n\n"
        "Important details to preserve:\nTemporal motion, camera trajectory, framing, "
        "shot rhythm, focus behavior, foreground/background relationships, lighting "
        "changes, style, color palette and final-frame feel.\n\n"
        + (extra_instruction + "\n\n" if extra_instruction else "")
        + "Return valid JSON only according to the required schema."
    )

    native_error: Exception | None = None
    try:
        return await _analyze_native(
            client,
            video_url=video_url,
            filename=filename,
            user_instruction=user_instruction,
        )
    except Exception as exc:  # noqa: BLE001 - provider fallback boundary
        native_error = exc

    if video_bytes is None:
        video_bytes = await _download_video_bytes(client, video_url)

    frames = await asyncio.to_thread(
        _extract_frame_data_urls_sync,
        video_bytes,
        duration_seconds=duration,
        max_frames=VIDEO_PROMPT_FRAME_COUNT,
    )
    try:
        return await _analyze_frames(
            client,
            frame_data_urls=frames,
            user_instruction=user_instruction,
        )
    except Exception as frame_exc:  # noqa: BLE001 - provider fallback boundary
        raise PromptToolProviderError(
            f"Не удалось разобрать видео: native={native_error}; frames={frame_exc}"
        ) from frame_exc
