from __future__ import annotations

import re


def prompt_length_error(max_length: int) -> str:
    """Stable safe code; the maximum comes from the provider response."""
    return f"prompt_too_long:max_length={max_length}"


def prompt_length_failure_message(error: str | None) -> str | None:
    """Render only the approved error code, never arbitrary provider text."""
    match = re.fullmatch(r"prompt_too_long:max_length=([1-9][0-9]{0,8})", error or "")
    if match is None:
        return None
    return (
        f"Промпт слишком длинный. Максимум — {match.group(1)} символов. "
        "Сократите текст и повторите генерацию."
    )
