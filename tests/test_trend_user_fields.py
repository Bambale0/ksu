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
