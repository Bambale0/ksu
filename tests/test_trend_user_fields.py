import json
from pathlib import Path

import pytest

from app.services.trend_user_fields import (
    TrendUserFieldsError,
    normalize_trend_user_fields,
    render_trend_prompt,
)


@pytest.mark.parametrize("label", [
    "Время года",
    "Время года (пример:зима)",
    "Время года (пример:лето)",
    "Время года (пример:весна)",
    "  ВРЕМЯ   ГОДА  ",
])
@pytest.mark.parametrize("configured", [False, True])
def test_season_accepts_cyrillic_for_configured_and_legacy_fields(label, configured):
    # Existing records can contain the incorrectly inferred number type.
    raw = [{"key": label, "label": label, "type": "number"}] if configured else None
    prompt = "Portrait in {{"+label+"}}"
    fields = normalize_trend_user_fields(raw, prompt=prompt)

    assert fields[0]["type"] == "text"
    rendered = render_trend_prompt(prompt, fields, {label.strip(): "зима"})
    assert "Portrait in зима" in rendered
    assert "{{" not in rendered


@pytest.mark.parametrize("label, expected", [
    ("Возраст", "number"),
    ("Год рождения", "number"),
    ("Количество свечей", "number"),
    ("Дата", "date"),
    ("Имя", "text"),
    ("Возраст в это время года", "number"),
    ("Дата и время года", "date"),
    ("Время года и возраст", "number"),
])
def test_season_fix_preserves_other_field_types(label, expected):
    fields = normalize_trend_user_fields([{"key": label, "label": label}], prompt="Portrait")

    assert fields[0]["type"] == expected
    if expected == "number":
        with pytest.raises(TrendUserFieldsError, match="должно быть числом"):
            render_trend_prompt("Portrait", fields, {label: "зима"})

CATALOG = json.loads(
    (Path(__file__).parent / "fixtures/trend_user_fields_catalog_20261021.json").read_text()
)


@pytest.mark.parametrize("entry", CATALOG["labels"], ids=lambda entry: entry["label"])
@pytest.mark.parametrize("configured", [False, True])
def test_reviewed_catalog_field_types(entry, configured):
    label = entry["label"]
    raw = [{"key": label, "label": label, "type": "number"}] if configured else None
    fields = normalize_trend_user_fields(raw, prompt="{{" + label + "}}")

    assert fields[0]["type"] == entry["expected_type"]


@pytest.mark.parametrize("label, expected", [["Погода (пример:солнечно)","text"],["Погода весной","text"],["Сезон: зима/весна/лето/осень","text"],["Предпочитаемое время года","text"],["Палитра","text"],["Пространство","text"],["Свечение","text"],["Летний образ","text"],["Весенний стиль","text"],["Цвет свечей","text"],["Надпись: Happy Birthday 31","text"],["Надпись на торте цифрами","text"],["Update style","text"],["Candidate","text"],["Надпись на торте (пример: 2026 год)","text"],["Возраст (пример:31)","number"],["Количество свечей","number"],["Число (пример:31st Birthday)","number"],["Дата рождения (пример:2020-12-01)","date"],["День рождения","date"],["birthday","date"],["Шары (красные) цифры","number"],["Год рождения в это время года","number"],["Дата (число/месяц/год)","date"],["Номер","number"]])
def test_field_examples_and_word_fragments_do_not_choose_keyboard(label, expected):
    fields = normalize_trend_user_fields([{"key": label, "label": label}], prompt="Portrait")

    assert fields[0]["type"] == expected
