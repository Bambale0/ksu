from pathlib import Path

from app.services.trend_collections import TrendCollectionService


def _source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_default_folders_keep_live_trends_separate_from_categories() -> None:
    collections = TrendCollectionService.default_collections()

    assert [item["id"] for item in collections] == ["trends", "birthday"]
    assert collections[0]["system_key"] == "trends"
    assert collections[0]["title"] == "Тренды"
    assert "Instagram" in collections[0]["description"]
    assert collections[1]["system_key"] == "birthday"
    assert collections[1]["title"] == "День рождения"


def test_admin_can_add_arbitrary_category_folders() -> None:
    state = TrendCollectionService.merge_state(
        {
            "collections": [
                {
                    "id": "folder-march-8",
                    "title": "8 марта",
                    "description": "Праздничные идеи",
                    "sort_order": 20,
                    "is_active": True,
                }
            ],
            "assignments": {"trend-1": "folder-march-8"},
        }
    )

    assert [item["title"] for item in state["collections"]] == [
        "Тренды",
        "День рождения",
        "8 марта",
    ]
    assert state["assignments"]["trend-1"] == "folder-march-8"


def test_unassigned_trends_stay_in_live_trends() -> None:
    state = TrendCollectionService.merge_state(None)

    assert TrendCollectionService.assigned_collection(state, "legacy-trend") == "trends"


def test_only_admin_manage_routes_can_mutate_folders() -> None:
    source = _source("app/api/v1/trend_collections.py")

    assert '@router.get("")' in source
    assert '@router.get("/{collection_id}/items")' in source
    assert '@router.post("/manage")' in source
    assert '@router.patch("/manage/{collection_id}")' in source
    assert '@router.delete("/manage/{collection_id}")' in source
    assert '@router.put("/manage/items/{trend_id}")' in source
    assert "await _inline_admin(session, user_id=user.id)" in source
    assert "AdminPolicy.authorize_action(account, \"social.moderate\", confirmed=True)" in source
    assert '@router.post("")' not in source


def test_folder_create_uses_stable_target_for_idempotent_replay() -> None:
    source = _source("app/api/v1/trend_collections.py")

    assert 'command_key = _command_key(idempotency_key, "folder-create")' in source
    assert "_stable_uuid(scope='folder', admin_id=account.id, command_key=command_key)" in source
    assert "idempotency_key=command_key" in source


def test_folder_trend_create_and_assignment_are_one_server_transaction() -> None:
    source = _source("app/api/v1/trend_collections.py")
    client = _source("frontend/mini-app/lib/trend-admin-api.ts")

    assert '@router.post("/manage/{collection_id}/items")' in source
    assert "session.add(item)" in source
    assert "await TrendCollectionService.assign_trend(" in source
    assert '"operation": "trend_collection.create_item"' in source
    assert "/api/v1/trend-collections/manage/${encodeURIComponent(collectionId)}/items" in client
    assert "trendCollectionsApi.assign" not in client


def test_pending_folder_target_is_ephemeral_and_cleared_with_editor_lifecycle() -> None:
    client = _source("frontend/mini-app/lib/trend-admin-api.ts")
    admin = _source("frontend/mini-app/components/trend-collection-admin.tsx")

    assert "sessionStorage" not in client
    assert "sessionStorage" not in admin
    assert "setTrendCollectionTarget(collectionId)" in admin
    assert "watchTrendEditorLifecycle()" in admin
    assert "clearTrendCollectionTarget()" in admin


def test_home_category_ux_has_unlabeled_grid_photo_video_tabs_and_trend_launcher() -> None:
    source = _source("frontend/mini-app/components/home-trend-folders.tsx")
    admin = _source("frontend/mini-app/components/trend-collection-admin.tsx")
    page = _source("frontend/mini-app/app/page.tsx")

    assert 'aria-label="Категории шаблонов"' in source
    assert '"Папки трендов"' not in source
    assert "← Категории" in source
    assert 'folder.system_key !== "trends"' in source
    assert "Фото ·" in source
    assert "Видео ·" in source
    assert "/mini-app/trend/?id=" in source
    assert "TrendCollectionAdmin" in source
    assert "＋ Новая категория" in admin
    assert "Готовые шаблоны" in admin
    assert "Хэштеги категории" in admin
    assert "Управление трендами" in admin
    assert "HomeTrendFolders" in page


def test_mini_app_admin_can_edit_reassign_and_hide_existing_trends() -> None:
    admin = _source("frontend/mini-app/components/trend-collection-admin.tsx")
    client = _source("frontend/mini-app/lib/trend-admin-api.ts")

    assert "Boolean(me.is_admin)" in admin
    assert "trendAdminApi.update(original.id" in admin
    assert "...original.payload" in admin
    assert "tags: parseTags(editingTrend.tags)" in admin
    assert "trendCollectionsApi.assign(trendId, collectionId)" in admin
    assert "trendAdminApi.hide(trend.id)" in admin
    assert "trendAdminApi.activate(trend.id)" in admin
    assert "Старые фото и видео не нужно загружать заново" in admin
    assert "trend-admin-edit-${trend.id}" in admin
    assert "trend-admin-visibility-${trend.id}" in admin
    assert "/api/v1/trends/manage/${encodeURIComponent(id)}" in client
    assert "/activate" in client


def test_top_live_trends_are_real_api_cards_not_legacy_model_sections() -> None:
    source = _source("frontend/mini-app/components/live-trend-rail.tsx")
    page = _source("frontend/mini-app/app/page.tsx")

    assert "roxy-home-live-trends" in source
    assert 'window.location.assign(`/mini-app/trend/?id=${encodeURIComponent(trend.id)}`)' in source
    assert "HomeTrendOrder" not in page
