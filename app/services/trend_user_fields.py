from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

MAX_USER_FIELDS = 6
MAX_FIELD_VALUE_LENGTH = 160
DEFAULT_TEXT_MAX_LENGTH = 80
_NUMBER_RE = re.compile(r"^-?\d+(?:[\.,]\d+)?$")
_TEMPLATE_RE = re.compile(r"\{\{([^{}]{1,64})\}\}")


class TrendUserFieldsError(ValueError):
    pass


def normalize_trend_user_fields(raw_fields: Any, *, prompt: str) -> list[dict[str, Any]]:
    if raw_fields in (None, ""):
        return []
    if not isinstance(raw_fields, list) or len(raw_fields) > MAX_USER_FIELDS:
        raise TrendUserFieldsError("Поля пользователя настроены неверно")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_fields:
        if not isinstance(raw, Mapping):
            raise TrendUserFieldsError("Поля пользователя настроены неверно")
        key = str(raw.get("key") or "").strip()
        label = str(raw.get("label") or key).strip()
        field_type = str(raw.get("type") or "text").strip().lower()
        if not key or len(key) > 48 or "{{" in key or "}}" in key or key in seen:
            raise TrendUserFieldsError("Поля пользователя настроены неверно")
        if not label or len(label) > 64 or field_type not in {"text", "number"}:
            raise TrendUserFieldsError("Поля пользователя настроены неверно")
        token = "{{" + key + "}}"
        if token not in prompt:
            raise TrendUserFieldsError(f"Добавьте {token} в скрытый промпт")
        try:
            max_length = int(raw.get("max_length") or DEFAULT_TEXT_MAX_LENGTH)
        except (TypeError, ValueError):
            max_length = DEFAULT_TEXT_MAX_LENGTH
        max_length = max(1, min(MAX_FIELD_VALUE_LENGTH, max_length))
        def decimal(name: str) -> Decimal | None:
            value = raw.get(name)
            if value in (None, ""):
                return None
            try:
                return Decimal(str(value))
            except (InvalidOperation, ValueError):
                raise TrendUserFieldsError(f"Некорректные ограничения поля «{label}»") from None
        min_value = decimal("min")
        max_value = decimal("max")
        if min_value is not None and max_value is not None and min_value > max_value:
            raise TrendUserFieldsError(f"Некорректные ограничения поля «{label}»")
        item: dict[str, Any] = {
            "key": key,
            "label": label,
            "type": field_type,
            "required": bool(raw.get("required", True)),
            "placeholder": str(raw.get("placeholder") or "").strip()[:80],
        }
        if field_type == "text":
            item["max_length"] = max_length
        else:
            if min_value is not None:
                item["min"] = float(min_value) if min_value % 1 else int(min_value)
            if max_value is not None:
                item["max"] = float(max_value) if max_value % 1 else int(max_value)
        if raw.get("suffix") not in (None, ""):
            item["suffix"] = str(raw.get("suffix"))[:24]
        if raw.get("default_value") not in (None, ""):
            item["default_value"] = str(raw.get("default_value"))[:MAX_FIELD_VALUE_LENGTH]
        normalized.append(item)
        seen.add(key)
    return normalized


def clean_submitted_user_values(raw_values: Any) -> dict[str, str]:
    if raw_values in (None, ""):
        return {}
    if not isinstance(raw_values, Mapping) or len(raw_values) > MAX_USER_FIELDS:
        raise TrendUserFieldsError("Некорректные поля шаблона")
    cleaned: dict[str, str] = {}
    for raw_key, raw_value in raw_values.items():
        key = str(raw_key or "").strip()
        if not key or len(key) > 48 or isinstance(raw_value, (Mapping, list, tuple, set)):
            raise TrendUserFieldsError("Некорректные поля шаблона")
        value = str(raw_value if raw_value is not None else "").strip()
        if len(value) > MAX_FIELD_VALUE_LENGTH:
            raise TrendUserFieldsError(f"Слишком длинное значение поля «{key}»")
        cleaned[key] = value
    return cleaned


def render_trend_prompt(prompt: str, user_fields: list[dict[str, Any]], raw_values: Any) -> str:
    values = clean_submitted_user_values(raw_values)
    if not user_fields:
        if values:
            raise TrendUserFieldsError("Этот тренд не принимает дополнительные поля")
        return prompt
    allowed = {str(field["key"]) for field in user_fields}
    if set(values) - allowed:
        raise TrendUserFieldsError("Переданы лишние поля тренда")
    rendered = prompt
    for field in user_fields:
        key = str(field["key"])
        label = str(field.get("label") or key)
        value = values.get(key, "").strip()
        if not value:
            if field.get("required", True):
                raise TrendUserFieldsError(f"Заполните поле «{label}»")
        elif field.get("type") == "number":
            if not _NUMBER_RE.fullmatch(value):
                raise TrendUserFieldsError(f"Поле «{label}» должно быть числом")
            number = Decimal(value.replace(",", "."))
            min_value = field.get("min")
            max_value = field.get("max")
            if min_value is not None and number < Decimal(str(min_value)):
                raise TrendUserFieldsError(f"Поле «{label}» слишком маленькое")
            if max_value is not None and number > Decimal(str(max_value)):
                raise TrendUserFieldsError(f"Поле «{label}» слишком большое")
        elif len(value) > int(field.get("max_length") or DEFAULT_TEXT_MAX_LENGTH):
            raise TrendUserFieldsError(f"Поле «{label}» слишком длинное")
        rendered = rendered.replace("{{" + key + "}}", value)
    unresolved = _TEMPLATE_RE.search(rendered)
    if unresolved:
        raise TrendUserFieldsError(f"Шаблон содержит незаполненное поле «{unresolved.group(1).strip()}»")
    return rendered.strip()
