from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MAX_USER_FIELDS = 6
MAX_FIELD_KEY_LENGTH = 48
MAX_FIELD_LABEL_LENGTH = 64
MAX_FIELD_VALUE_LENGTH = 160

_TEMPLATE_RE = re.compile(r"\{\{([^{}]+)\}\}")
_NUMBER_RE = re.compile(r"^-?\d+(?:[\.,]\d+)?$")

# Whole words describe the input; examples and fragments of other words do not.
_NUMBER_FIELD_WORDS = frozenset(["возраст","возраста","число","числа","чисел","цифра","цифры","цифр","цифру","цифре","цифрами","количество","количества","номер","номера","номеров","рост","роста","вес","веса","лет","год","года","годы","годов","свеча","свечи","свечей","свечах"])
_DATE_FIELD_WORDS = frozenset(("дата", "date", "birthday", "birthdate"))
_TEXT_FIELD_START_WORDS = frozenset(["текст","надпись","фраза","слоган","имя","фамилия","название","цвет","оттенок","палитра","caption","text","name","title","color","colour"])
_EXAMPLE_WORDS = frozenset(("пример", "например", "example"))


class TrendUserFieldsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TrendUserFieldSpec:
    key: str
    label: str
    field_type: str
    required: bool = True
    max_length: int = MAX_FIELD_VALUE_LENGTH


def infer_field_type(label: str) -> str:
    normalized = str(label or "").strip().lower()
    # Remove nested explanations while retaining words after a parenthesis.
    while True:
        clean = re.sub(r"\([^()]*\)", " ", normalized)
        if clean == normalized:
            break
        normalized = clean
    normalized = normalized.split("(", 1)[0].split(":", 1)[0]
    words = re.findall(r"[^\W\d_]+", normalized)
    for index, word in enumerate(words):
        if word in _EXAMPLE_WORDS:
            words = words[:index]
            break
    if words and words[0] in _TEXT_FIELD_START_WORDS:
        return "text"

    # The phrase names a season, not a numeric year. Preserve other hints.
    semantic_words: list[str] = []
    index = 0
    while index < len(words):
        if words[index:index + 2] == ["время", "года"]:
            index += 2
        else:
            semantic_words.append(words[index])
            index += 1
    if _DATE_FIELD_WORDS.intersection(semantic_words) or any(
        semantic_words[index:index + 2] == ["день", "рождения"]
        for index in range(len(semantic_words) - 1)
    ):
        return "date"
    if _NUMBER_FIELD_WORDS.intersection(semantic_words):
        return "number"
    return "text"


def clean_submitted_user_values(raw_values: Any) -> dict[str, str]:
    if raw_values in (None, ""):
        return {}
    if not isinstance(raw_values, Mapping) or len(raw_values) > MAX_USER_FIELDS:
        raise TrendUserFieldsError("Некорректные поля шаблона")
    cleaned: dict[str, str] = {}
    for raw_key, raw_value in raw_values.items():
        key = str(raw_key or "").strip()
        if not key or len(key) > MAX_FIELD_KEY_LENGTH or isinstance(raw_value, (Mapping, list, tuple, set)):
            raise TrendUserFieldsError("Некорректные поля шаблона")
        value = str(raw_value if raw_value is not None else "").strip()
        if len(value) > MAX_FIELD_VALUE_LENGTH:
            raise TrendUserFieldsError(f"Слишком длинное значение поля «{key}»")
        cleaned[key] = value
    return cleaned


def _template_keys(prompt: str) -> tuple[str, ...]:
    keys: list[str] = []
    for match in _TEMPLATE_RE.finditer(str(prompt or "")):
        key = match.group(1).strip()
        if not key or len(key) > MAX_FIELD_KEY_LENGTH:
            continue
        if key not in keys:
            keys.append(key)
        if len(keys) >= MAX_USER_FIELDS:
            break
    return tuple(keys)


def _normalize_configured_fields(raw_fields: Any) -> list[dict[str, Any]]:
    if raw_fields in (None, ""):
        return []
    if not isinstance(raw_fields, list):
        raise TrendUserFieldsError("Поля шаблона настроены неверно")
    if len(raw_fields) > MAX_USER_FIELDS:
        raise TrendUserFieldsError(f"В одном тренде можно использовать не больше {MAX_USER_FIELDS} полей")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_field in raw_fields:
        if not isinstance(raw_field, Mapping):
            raise TrendUserFieldsError("Поля шаблона настроены неверно")
        label = str(raw_field.get("label") or raw_field.get("key") or "").strip()
        key = str(raw_field.get("key") or label).strip()
        if (
            not key
            or not label
            or len(key) > MAX_FIELD_KEY_LENGTH
            or len(label) > MAX_FIELD_LABEL_LENGTH
            or "{{" in key
            or "}}" in key
        ):
            raise TrendUserFieldsError("Поля шаблона настроены неверно")
        dedupe_key = key.casefold()
        if dedupe_key in seen:
            raise TrendUserFieldsError("Поля шаблона не должны повторяться")
        seen.add(dedupe_key)
        normalized.append(
            {
                "key": key,
                "label": label,
                "type": infer_field_type(label),
                "required": True,
                "max_length": MAX_FIELD_VALUE_LENGTH,
            }
        )
    return normalized


def normalize_trend_user_fields(raw_fields: Any, *, prompt: str) -> list[dict[str, Any]]:
    """Normalize admin-selected fields, falling back to legacy {{...}} tokens."""

    fields = _normalize_configured_fields(raw_fields)
    if fields:
        return fields
    return [
        {
            "key": key,
            "label": key,
            "type": infer_field_type(key),
            "required": True,
            "max_length": MAX_FIELD_VALUE_LENGTH,
        }
        for key in _template_keys(prompt)
    ]


def _field_specs(user_fields: list[dict[str, Any]]) -> tuple[TrendUserFieldSpec, ...]:
    return tuple(
        TrendUserFieldSpec(
            key=str(field["key"]),
            label=str(field.get("label") or field["key"]),
            field_type=str(field.get("type") or infer_field_type(str(field["key"]))),
            required=bool(field.get("required", True)),
            max_length=MAX_FIELD_VALUE_LENGTH,
        )
        for field in user_fields
    )


def _validated_field_value(spec: TrendUserFieldSpec, raw_value: str) -> str:
    value = str(raw_value or "").strip()
    if not value:
        if spec.required:
            raise TrendUserFieldsError(f"Заполните поле «{spec.label}»")
        return ""
    if spec.field_type == "number" and not _NUMBER_RE.fullmatch(value):
        raise TrendUserFieldsError(f"Поле «{spec.label}» должно быть числом")
    if len(value) > spec.max_length:
        raise TrendUserFieldsError(
            f"Поле «{spec.label}» должно быть короче {spec.max_length + 1} символов"
        )
    return value


def render_trend_prompt(prompt: str, user_fields: list[dict[str, Any]], raw_values: Any) -> str:
    """Apply user values server-side without exposing or requiring prompt tokens."""

    base_prompt = str(prompt or "").strip()
    values = clean_submitted_user_values(raw_values)
    specs = _field_specs(user_fields)
    if not specs:
        if values:
            raise TrendUserFieldsError("Этот тренд не принимает дополнительные поля")
        return base_prompt

    allowed = {spec.key for spec in specs}
    if set(values) - allowed:
        raise TrendUserFieldsError("Переданы лишние поля тренда")

    validated = {
        spec.key: _validated_field_value(spec, values.get(spec.key, ""))
        for spec in specs
    }

    # A callable replacement preserves backslashes and never re-expands user text.
    rendered = _TEMPLATE_RE.sub(
        lambda match: validated.get(match.group(1).strip(), match.group(0)),
        base_prompt,
    )

    overrides = "\n".join(
        f"- {spec.label}: {validated[spec.key]}"
        for spec in specs
        if validated[spec.key]
    )
    if overrides:
        rendered = (
            f"{rendered}\n\n"
            "ВАЖНО: примените следующие параметры пользователя как приоритетные "
            "изменения. Если они противоречат исходному prompt, значения ниже имеют "
            f"приоритет. Остальные детали сохраните без изменений:\n{overrides}"
        )
    return rendered.strip()
