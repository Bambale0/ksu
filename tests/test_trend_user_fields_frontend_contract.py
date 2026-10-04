from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_personalized_trend_fields_follow_tanyapi_auto_field_architecture() -> None:
    service = read("app/services/trends.py")
    field_service = read("app/services/trend_user_fields.py")
    api = read("app/api/v1/trends.py")
    page = read("frontend/mini-app/app/trend/page.tsx")
    client = read("frontend/mini-app/lib/api.ts")
    admin = read("frontend/mini-app/components/inline-trend-admin.tsx")

    assert '"user_fields": recipe["user_fields"]' in service
    assert 'render_trend_prompt(recipe["prompt"], recipe["user_fields"], user_values)' in service
    assert 'user_values=payload.user_values' in api
    assert 'api.runTrend(' in page
    assert 'const aspectRatioReady = !aspectRatioOptions.length || Boolean(selectedAspectRatio);' in page
    assert '...(selectedAspectRatio ? { aspectRatio: selectedAspectRatio } : {})' in page
    assert 'user_values: userValues' in client
    assert 'resolution: options.resolution' in client
    assert 'aspect_ratio: options.aspectRatio' in client
    assert 'prompt:' not in client[client.index('runTrend:'):client.index('promptTools:')]

    assert 'TEMPLATE_FIELD_PRESETS = ["Возраст", "Имя", "Надпись", "Дата", "Число"]' in admin
    assert 'Поля шаблона' in admin
    assert 'Другое поле, например: Цвет волос' in admin
    assert 'inferTemplateFieldType' in admin
    assert 'user_fields: userFields.length ? userFields : undefined' in admin
    assert 'Добавьте {{' not in admin
    assert '>Тип<' not in admin
    assert '>Минимум<' not in admin
    assert '>Максимум<' not in admin

    assert 'def infer_field_type(label: str) -> str:' in field_service
    assert 'ВАЖНО: примените следующие параметры пользователя' in field_service
    assert 'falling back to legacy {{...}} tokens' in field_service


def test_runner_fields_are_empty_and_number_validation_matches_backend() -> None:
    page = read("frontend/mini-app/app/trend/page.tsx")
    backend = read("app/services/trend_user_fields.py")
    types = read("frontend/mini-app/lib/types.ts")

    assert 'map((field) => [field.key, ""])' in page
    assert 'field.type === "date" ? "date" : "text"' in page
    assert 'const TREND_USER_NUMBER_RE = /^-?\\d+(?:[.,]\\d+)?$/;' in page
    assert 'if (field.type === "number") return TREND_USER_NUMBER_RE.test(clean);' in page
    assert '_NUMBER_RE = re.compile(r"^-?\\d+(?:[\\.,]\\d+)?$")' in backend
    assert 'type: "text" | "number" | "date";' in types
    assert 'default_value?: string;' not in types


def test_existing_trend_can_be_upgraded_with_user_fields_without_new_id() -> None:
    admin = read("frontend/mini-app/components/inline-trend-admin.tsx")
    client = read("frontend/mini-app/lib/trend-admin-api.ts")
    manager = read("app/api/v1/admin_trends.py")

    assert 'Array.isArray(payload.user_fields) ? payload.user_fields.slice(0, 6) : []' in admin
    assert 'setEditingId(duplicate ? null : item.id)' in admin
    assert 'if (editingId) await trendAdminApi.update(editingId, body);' in admin
    assert 'update: (id: string, body: TrendWriteBody)' in client
    assert '`/api/v1/trends/manage/${encodeURIComponent(id)}`' in client
    assert 'select(AdminTrend).where(AdminTrend.id == trend_id).with_for_update()' in manager
    assert 'item.payload = recipe' in manager
    assert 'item.title = title' in manager


def test_trend_runner_requires_model_owned_aspect_ratio_before_launch() -> None:
    api = read("app/api/v1/trends.py")
    service = read("app/services/trends.py")
    page = read("frontend/mini-app/app/trend/page.tsx")
    client = read("frontend/mini-app/lib/api.ts")
    types = read("frontend/mini-app/lib/types.ts")
    social = read("frontend/mini-app/components/roxy-social-app.tsx")
    telegram = read("app/bot/handlers/trends.py")

    assert "aspect_ratio: str | None = Field(default=None, max_length=16)" in api
    assert "aspect_ratio=payload.aspect_ratio" in api
    assert '"aspect_ratio_options": TrendService._aspect_ratio_options(recipe)' in service
    assert 'value.lower() in {"auto", "adaptive"}' in service
    assert 'raise TrendRecipeError("Aspect ratio is required")' in service
    assert 'raise TrendRecipeError("Unsupported aspect ratio")' in service
    assert 'parameters["aspect_ratio"] = selected' in service

    assert 'aspect_ratio_options?: string[];' in types
    assert 'Формат кадра *' in page
    assert 'role="radiogroup" aria-label="Формат кадра"' in page
    assert 'const [selectedAspectRatio, setSelectedAspectRatio] = useState("");' in page
    assert 'disabled={!ready || uploading || running}' in page
    assert 'aspect_ratio: options.aspectRatio' in client

    assert social.count("api.runTrend(") == 0
    assert social.count("/mini-app/trend/?id=") >= 2
    assert "/mini-app/trend/" in telegram
    assert "urlencode({'id': trend_id})" in telegram
