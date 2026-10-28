from __future__ import annotations

from app.db.models import Generation


SEEDANCE_AUTHOR_REPLAY_MODEL_ID = "seedance-2.5"
SEEDANCE_AUTHOR_REPLAY_PROMPT_MAX_CHARS = 30_000
SEEDANCE_AUTHOR_REPLAY_PROMPT_MAX_BYTES = 40_000
PRIVATE_AUTHOR_REPLAY_MARKER = "_private_author_recipe_replay"


def is_private_seedance_author_replay(generation: Generation) -> bool:
    return bool((generation.parameters or {}).get(PRIVATE_AUTHOR_REPLAY_MARKER))


def seedance_identity_requirements(*, source_image_count: int) -> dict[str, int | bool]:
    """Describe the viewer-owned media needed to replay an author's Seedance recipe.

    The author's video, when present, is restored privately by the server. The
    viewer only supplies identity photos. A photo is required even for a source
    that was originally text-only so the repeat can actually replace the person.
    """

    return {
        "image_count": max(1, int(source_image_count)),
        "video_count": 0,
        "audio_count": 0,
        "required": True,
    }


def build_seedance_motion_identity_prompt(
    original_prompt: str,
    *,
    identity_count: int,
    max_chars: int = SEEDANCE_AUTHOR_REPLAY_PROMPT_MAX_CHARS,
    max_bytes: int = SEEDANCE_AUTHOR_REPLAY_PROMPT_MAX_BYTES,
) -> str:
    """Assign motion to the author's video and identity to the viewer's photos."""

    if identity_count < 1:
        raise ValueError("At least one identity photo is required")

    identity_tags = ", ".join(f"@Image{index}" for index in range(1, identity_count + 1))
    result = (
        "@Video1 is the authoritative source for motion, timing, camera movement, "
        "composition, and scene continuity.\n"
        f"{identity_tags} are the authoritative identity references for the main person.\n"
        "Replace the main person's identity with the identity from the image references "
        "while preserving the action and scene from @Video1. Do not copy the person's "
        "facial identity or distinctive appearance from @Video1.\n\n"
        "Original generation instruction:\n"
        f"{original_prompt.strip()}"
    )
    if len(result) > max_chars:
        raise ValueError(
            "The source prompt is too long to add Seedance motion and identity instructions"
        )
    if len(result.encode("utf-8")) > max_bytes:
        raise ValueError(
            "The source prompt is too large in UTF-8 to add Seedance motion and identity instructions"
        )
    return result


def seedance_motion_original_prompt_max_chars(
    *,
    identity_count: int,
    max_chars: int = SEEDANCE_AUTHOR_REPLAY_PROMPT_MAX_CHARS,
) -> int:
    """Return the original-prompt budget after reserving the role wrapper."""

    empty_wrapped = build_seedance_motion_identity_prompt(
        "",
        identity_count=identity_count,
        max_chars=max_chars,
    )
    return max_chars - len(empty_wrapped)
