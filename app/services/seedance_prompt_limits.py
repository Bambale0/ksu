from __future__ import annotations

SEEDANCE_20_PROMPT_MAX_CHARS = 20_000
SEEDANCE_25_PROMPT_MAX_CHARS = 30_000
DEFAULT_GENERATION_PROMPT_MAX_CHARS = 8_000

SEEDANCE_20_MODEL_IDS = frozenset({
    "seedance-2.0",
    "seedance-2.0-fast",
    "seedance-2.0-mini",
    "bytedance/seedance-2",
    "bytedance/seedance-2-fast",
    "bytedance/seedance-2-mini",
})
SEEDANCE_25_MODEL_IDS = frozenset({"seedance-2.5", "bytedance/seedance-2-5"})


def prompt_max_chars(model_id: str) -> int:
    key = str(model_id or "").strip()
    if key in SEEDANCE_20_MODEL_IDS:
        return SEEDANCE_20_PROMPT_MAX_CHARS
    if key in SEEDANCE_25_MODEL_IDS:
        return SEEDANCE_25_PROMPT_MAX_CHARS
    return DEFAULT_GENERATION_PROMPT_MAX_CHARS


def validate_prompt_length(model_id: str, prompt: object) -> str:
    value = str(prompt or "")
    limit = prompt_max_chars(model_id)
    if len(value) > limit:
        raise ValueError(f"Prompt for {model_id} must be at most {limit} characters")
    return value
