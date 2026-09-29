from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from app.services.neironych_video_contracts import (
    NeironychVideoContractError,
    normalize_neironych_video_input,
)


class SeedanceWizardError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SeedanceTestSpec:
    model_name: str
    min_duration: int
    max_duration: int
    resolutions: tuple[str, ...]
    max_image_refs: int
    max_video_refs: int
    max_audio_refs: int
    max_total_refs: int
    supports_edit: bool


_FIXED_ASPECT_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4", "21:9")
_ASPECT_RATIO_RE = re.compile(
    rf"(?<!\\d)(?:{'|'.join(re.escape(value) for value in _FIXED_ASPECT_RATIOS)})(?!\\d)"
)


def _single_prompt_aspect_ratio(prompt: str) -> str | None:
    values = {match.group(0) for match in _ASPECT_RATIO_RE.finditer(prompt)}
    if len(values) == 1:
        return next(iter(values))
    return None


_SPECS: dict[str, SeedanceTestSpec] = {
    "seedance-2.0": SeedanceTestSpec(
        model_name="seedance-2.0",
        min_duration=4,
        max_duration=15,
        resolutions=("480p", "720p", "1080p", "4k"),
        max_image_refs=9,
        max_video_refs=3,
        max_audio_refs=3,
        max_total_refs=12,
        supports_edit=False,
    ),
    "seedance-2.5": SeedanceTestSpec(
        model_name="seedance-2.5",
        min_duration=4,
        max_duration=30,
        resolutions=("480p", "720p", "1080p"),
        max_image_refs=30,
        max_video_refs=10,
        max_audio_refs=10,
        max_total_refs=50,
        supports_edit=True,
    ),
}


def get_seedance_test_spec(model_name: str) -> SeedanceTestSpec:
    try:
        return _SPECS[str(model_name or "").strip()]
    except KeyError as exc:
        raise SeedanceWizardError("Неизвестная модель Seedance.") from exc


def build_seedance_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    model_name = str(data.get("model_name") or "").strip()
    spec = get_seedance_test_spec(model_name)
    mode = str(data.get("mode") or "").strip()
    if mode not in {"text", "reference", "frame", "edit"}:
        raise SeedanceWizardError("Выберите режим Seedance.")
    if mode == "edit" and not spec.supports_edit:
        raise SeedanceWizardError("Edit доступен только в Seedance 2.5.")

    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        raise SeedanceWizardError("Введите промпт.")

    resolution = str(data.get("resolution") or "").strip()
    if resolution not in spec.resolutions:
        raise SeedanceWizardError("Выберите разрешение.")

    payload: dict[str, Any] = {
        "prompt": prompt,
        "resolution": resolution,
    }

    if mode != "edit":
        try:
            duration = int(data.get("duration"))
        except (TypeError, ValueError) as exc:
            raise SeedanceWizardError("Выберите длительность.") from exc
        if not spec.min_duration <= duration <= spec.max_duration:
            raise SeedanceWizardError(
                f"Длительность: {spec.min_duration}–{spec.max_duration} сек."
            )
        payload["duration"] = duration

        aspect_ratio = str(data.get("aspect_ratio") or "").strip()
        if mode == "frame":
            aspect_ratio = "adaptive"
        elif not aspect_ratio:
            raise SeedanceWizardError("Выберите соотношение сторон.")
        else:
            prompt_ratio = _single_prompt_aspect_ratio(prompt)
            if prompt_ratio is not None and prompt_ratio != aspect_ratio:
                raise SeedanceWizardError(
                    "В промпте явно указан формат "
                    f"{prompt_ratio}, а в параметрах выбран {aspect_ratio}. "
                    "Выберите совпадающее соотношение сторон или уберите "
                    "однозначное указание формата из промпта."
                )
        payload["aspect_ratio"] = aspect_ratio

    images = list(data.get("reference_images") or [])
    videos = list(data.get("reference_videos") or [])
    audios = list(data.get("reference_audios") or [])

    if mode in {"reference", "edit"}:
        if images:
            payload["reference_images"] = [{"url": str(url)} for url in images]
        if videos:
            payload["reference_videos"] = [{"url": str(url)} for url in videos]
        if audios:
            payload["reference_audios"] = [{"url": str(url)} for url in audios]

    if mode == "frame":
        start_image = str(data.get("start_image") or "").strip()
        end_image = str(data.get("end_image") or "").strip()
        if not start_image:
            raise SeedanceWizardError("Frame mode требует стартовое изображение.")
        payload["start_image"] = {"url": start_image}
        if end_image:
            payload["end_image"] = {"url": end_image}

    if mode == "reference" and model_name == "seedance-2.5":
        payload["omni_reference_task_type"] = "reference"
    elif mode == "edit":
        payload["omni_reference_task_type"] = "edit"

    # Neironych currently accepts generate_audio=true, while false is rejected.
    # Keep the field explicit for reference/edit wizard modes where audio output
    # is part of the documented contract.
    if mode in {"reference", "edit"}:
        payload["generate_audio"] = True

    try:
        normalized = normalize_neironych_video_input(model_name, payload)
    except NeironychVideoContractError as exc:
        raise SeedanceWizardError(str(exc)) from exc

    # Prompt is validated here for length/reference integrity, but the durable
    # enqueue boundary owns the trusted prompt value and injects it again.
    normalized.pop("prompt", None)
    return normalized


def reference_counts(data: Mapping[str, Any]) -> tuple[int, int, int]:
    return (
        len(list(data.get("reference_images") or [])),
        len(list(data.get("reference_videos") or [])),
        len(list(data.get("reference_audios") or [])),
    )
