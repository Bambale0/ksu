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


def kling4_public_failure_message(error: str | None) -> str | None:
    """Translate Kling 4.0 failures without disclosing supplier internals.

    Provider-specific errors remain stored for operations/reconciliation. The
    Mini App and Telegram present only stable product-level explanations.
    """
    if not error:
        return None
    prompt_message = prompt_length_failure_message(error)
    if prompt_message:
        return prompt_message

    lowered = error.casefold()
    if any(marker in lowered for marker in (
        "credits insufficient", "недостаточно кредитов",
        "supplier_balance", "insufficient balance", "402",
        "rox не списаны", "создание видео временно недоступно",
    )):
        return "Создание видео временно недоступно. Попробуйте повторить позже."
    if "timeout" in lowered or "timed out" in lowered or "таймаут" in lowered:
        return "Создание видео заняло слишком много времени. Попробуйте ещё раз."
    if any(marker in lowered for marker in ("copyright", "moderation", "safety", "policy", "content policy")):
        return "Исходные материалы или описание не прошли проверку. Попробуйте изменить запрос."
    if any(marker in lowered for marker in ("validation", "invalid", "required", "unsupported", "contract")):
        return "Не удалось создать видео с выбранными настройками. Проверьте параметры и попробуйте ещё раз."
    return "Не удалось создать видео. Попробуйте повторить позже."
