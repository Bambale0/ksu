"""Opt-in named reference contracts. Legacy recipes never acquire slots on read."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit


REFERENCE_TOKEN = re.compile(r"(?<![\w@])@?(image|video)_?([1-9][0-9]*)(?!\w)", re.I)


def extract_reference_slots(prompt: str) -> list[dict[str, Any]]:
    """Suggestions only; an administrator must explicitly persist the schema."""
    found: dict[str, dict[str, Any]] = {}
    for match in REFERENCE_TOKEN.finditer(prompt):
        kind, index = match.group(1).lower(), int(match.group(2))
        if index > 16:
            raise ValueError("Номер референса превышает возможности шаблона")
        for number in range(1, index + 1):
            slot_id = f"{kind}_{number}"
            found.setdefault(
                slot_id,
                {
                    "id": slot_id,
                    "label": f"{'Фото' if kind == 'image' else 'Видео'} {number}",
                    "description": "",
                    "kind": kind,
                    "source": "user",
                    "required": True,
                },
            )
    slots = sorted(found.values(), key=lambda slot: (slot["kind"], int(slot["id"].split("_")[1])))
    return [{**slot, "order": order} for order, slot in enumerate(slots)]


def normalize_reference_schema(raw: Any, *, prompt: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or raw.get("mode") not in {"strict", "range"}:
        raise ValueError("Выберите строгий режим или диапазон референсов")
    source = raw.get("slots")
    if not isinstance(source, list) or not 1 <= len(source) <= 16:
        raise ValueError("Добавьте от 1 до 16 именных референсов в пределах возможностей модели")
    slots: list[dict[str, Any]] = []
    indexes = {"image": 0, "video": 0}
    optional_seen = {"image": False, "video": False}
    for order, slot in enumerate(source):
        if not isinstance(slot, dict):
            raise ValueError("Некорректный референс")
        kind, origin = slot.get("kind"), slot.get("source", "user")
        if kind not in indexes or origin not in {"user", "admin"}:
            raise ValueError("Референс должен быть фото или видео с указанным источником")
        indexes[kind] += 1
        slot_id = f"{kind}_{indexes[kind]}"
        if (
            slot.get("id") != slot_id
            or type(slot.get("order")) is not int
            or slot["order"] != order
        ):
            raise ValueError("Проверьте идентификаторы и порядок референсов")
        label, description = (
            str(slot.get("label") or "").strip(),
            str(slot.get("description") or "").strip(),
        )
        if not label or len(label) > 64 or len(description) > 240:
            raise ValueError("Укажите название референса до 64 символов и описание до 240 символов")
        required = slot.get("required", True)
        if type(required) is not bool or (raw["mode"] == "strict" and not required):
            raise ValueError("В строгом режиме обязательны все референсы")
        if origin == "admin" and not required:
            raise ValueError("Заранее заданный референс всегда обязателен")
        if optional_seen[kind] and required:
            raise ValueError("Необязательные референсы должны идти последними для своего типа")
        optional_seen[kind] |= not required
        clean = {
            "id": slot_id,
            "label": label,
            "description": description,
            "kind": kind,
            "source": origin,
            "order": order,
            "required": required,
        }
        url = slot.get("url")
        if origin == "admin":
            parsed = urlsplit(str(url or ""))
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Загрузите заранее заданный референс")
            clean["url"] = str(url)
        elif url:
            raise ValueError("Пользовательский слот не может содержать заранее заданный URL")
        slots.append(clean)
    by_id = {slot["id"]: slot for slot in slots}
    for match in REFERENCE_TOKEN.finditer(prompt):
        slot_id = f"{match.group(1).lower()}_{int(match.group(2))}"
        if slot_id not in by_id or not by_id[slot_id]["required"]:
            raise ValueError(f"Ссылка {slot_id} в промпте требует обязательного референса")
    return {"mode": raw["mode"], "slots": slots}


def user_slots(schema: dict[str, Any], kind: str | None = None) -> list[dict[str, Any]]:
    return [
        s for s in schema["slots"] if s["source"] == "user" and (kind is None or s["kind"] == kind)
    ]


def public_reference_schema(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": schema["mode"],
        "slots": [
            {key: value for key, value in slot.items() if key != "url"} for slot in schema["slots"]
        ],
    }


def resolve_reference_inputs(
    schema: dict[str, Any], inputs: list[dict[str, str]] | None
) -> tuple[list[str], list[str]]:
    if inputs is None:
        raise ValueError("Загрузите референсы в соответствующие именные поля")
    expected = user_slots(schema)
    declared = {slot["id"]: slot for slot in expected}
    received: dict[str, str] = {}
    orders: list[int] = []
    for entry in inputs:
        slot = declared.get(entry.get("slot_id", ""))
        if slot is None or slot["id"] in received or entry.get("kind") != slot["kind"]:
            raise ValueError("Неизвестный, повторный или неверный тип референса")
        url = entry.get("url", "")
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Загрузите файл референса заново")
        received[slot["id"]] = url
        orders.append(slot["order"])
    if orders != sorted(orders):
        raise ValueError("Порядок референсов не соответствует шаблону")
    for slot in expected:
        if slot["required"] and slot["id"] not in received:
            raise ValueError(f"Загрузите референс «{slot['label']}»")
    # Never compact across an absent middle slot, including a later preset.
    for kind in ("image", "video"):
        gap = False
        for slot in schema["slots"]:
            if slot["kind"] != kind:
                continue
            present = slot["source"] == "admin" or slot["id"] in received
            if gap and present:
                raise ValueError("Заполните референсы по порядку без пропусков")
            gap |= not present
    return tuple(
        [received[s["id"]] for s in expected if s["kind"] == kind and s["id"] in received]
        for kind in ("image", "video")
    )  # type: ignore[return-value]


def merge_reference_urls(schema: dict[str, Any], kind: str, urls: list[str]) -> list[str]:
    supplied = iter(urls)
    result = []
    for slot in schema["slots"]:
        if slot["kind"] == kind:
            url = slot["url"] if slot["source"] == "admin" else next(supplied, None)
            if url:
                result.append(url)
    return result
