from __future__ import annotations

import re

_TAG_RE = re.compile(
    r"@\s*(?P<kind>image|img|video|audio)\s*[_-]?\s*(?P<index>\d+)(?!\w)",
    re.IGNORECASE,
)


def canonicalize_seedance_reference_tags(
    prompt: str,
    *,
    image_count: int = 0,
    video_count: int = 0,
    audio_count: int = 0,
) -> str:
    text = str(prompt or "")
    images = max(0, int(image_count))
    videos = max(0, int(video_count))
    audios = max(0, int(audio_count))

    def replace(match: re.Match[str]) -> str:
        kind = match.group("kind").lower()
        index = int(match.group("index"))
        if kind in {"image", "img"}:
            if index > images and index > 0:
                overflow = index - images
                if 1 <= overflow <= videos:
                    return f"@Video{overflow}"
                overflow -= videos
                if 1 <= overflow <= audios:
                    return f"@Audio{overflow}"
            return f"@Image{index}"
        if kind == "video":
            return f"@Video{index}"
        return f"@Audio{index}"

    return _TAG_RE.sub(replace, text)


def missing_seedance_reference_tags(
    prompt: str,
    *,
    image_count: int = 0,
    video_count: int = 0,
    audio_count: int = 0,
) -> list[str]:
    limits = {
        "image": max(0, int(image_count)),
        "video": max(0, int(video_count)),
        "audio": max(0, int(audio_count)),
    }
    missing: list[str] = []
    canonical = canonicalize_seedance_reference_tags(
        prompt,
        image_count=image_count,
        video_count=video_count,
        audio_count=audio_count,
    )
    for match in _TAG_RE.finditer(canonical):
        kind = match.group("kind").lower()
        kind = "image" if kind == "img" else kind
        index = int(match.group("index"))
        if index < 1 or index > limits[kind]:
            tag = f"@{kind.title()}{index}"
            if tag not in missing:
                missing.append(tag)
    return missing


def seedance_reference_requirements(prompt: str) -> dict[str, int]:
    """Return the highest explicit typed slot index required by a template prompt."""

    required = {"image": 0, "video": 0, "audio": 0}
    for match in _TAG_RE.finditer(str(prompt or "")):
        kind = match.group("kind").lower()
        kind = "image" if kind == "img" else kind
        index = int(match.group("index"))
        if index > required[kind]:
            required[kind] = index
    return required
