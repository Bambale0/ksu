from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

def test_personalized_trend_fields_stay_private_and_server_owned() -> None:
    service = read("app/services/trends.py")
    api = read("app/api/v1/trends.py")
    page = read("frontend/mini-app/app/trend/page.tsx")
    client = read("frontend/mini-app/lib/api.ts")
    admin = read("frontend/mini-app/components/inline-trend-admin.tsx")
    assert '"user_fields": recipe["user_fields"]' in service
    assert 'render_trend_prompt(recipe["prompt"], recipe["user_fields"], user_values)' in service
    assert 'user_values=payload.user_values' in api
    assert 'api.runTrend(trend.id, references.map((item) => item.url), userValues)' in page
    assert 'user_values: userValues' in client
    assert 'user_fields: userFields.length ? userFields : undefined' in admin
    assert '{{${field.key}}}' in admin
    assert 'prompt:' not in client[client.index('runTrend:'):client.index('promptTools:')]

def test_existing_trend_can_be_upgraded_with_user_fields_without_new_id() -> None:
    admin = read("frontend/mini-app/components/inline-trend-admin.tsx")
    client = read("frontend/mini-app/lib/trend-admin-api.ts")
    manager = read("app/api/v1/admin_trends.py")

    # Legacy trends have no user_fields; editor must load them as an empty list.
    assert 'Array.isArray(payload.user_fields) ? payload.user_fields.slice(0, 6) : []' in admin
    # Edit mode keeps the original id and uses the update endpoint, not create.
    assert 'setEditingId(duplicate ? null : item.id)' in admin
    assert 'if (editingId) await trendAdminApi.update(editingId, body);' in admin
    assert 'update: (id: string, body: TrendWriteBody)' in client
    assert '`/api/v1/trends/manage/${encodeURIComponent(id)}`' in client
    # Backend updates the locked row in-place, preserving id/usage history.
    assert 'select(AdminTrend).where(AdminTrend.id == trend_id).with_for_update()' in manager
    assert 'item.payload = recipe' in manager
    assert 'item.title = title' in manager
