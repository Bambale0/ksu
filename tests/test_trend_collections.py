from pathlib import Path

from app.services.trend_collections import TrendCollectionService


def _source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_default_folders_keep_ai_reference_first_and_trends_separate() -> None:
    collections = TrendCollectionService.default_collections()

    assert [item["id"] for item in collections] == ["ai-reference", "trends", "birthday"]
    assert collections[0]["title"] == "AI РЕФЕРЕНС"
    assert "взрослый" in collections[0]["description"]
    assert "детский" in collections[0]["description"]
    assert "животных" in collections[0]["description"]
    assert "HD" in collections[0]["description"]
    assert "редактор" in collections[0]["description"]
    assert collections[1]["title"] == "Тренды"
    assert "Instagram" in collections[1]["description"]
    assert collections[2]["title"] == "День рождения"


def test_admin_can_add_arbitrary_folders_without_changing_system_folders() -> None:
    state = TrendCollectionService.merge_state(
        {
            "collections": [
                {
                    "id": "folder-march-8",
                    "title": "8 марта",
                    "description": "Праздничные идеи",
                    "sort_order": 30,
                    "is_active": True,
                }
            ],
            "assignments": {"trend-1": "folder-march-8"},
        }
    )

    assert [item["title"] for item in state["collections"]][:4] == [
        "AI РЕФЕРЕНС",
        "Тренды",
        "День рождения",
        "8 марта",
    ]
    assert state["assignments"]["trend-1"] == "folder-march-8"


def test_unassigned_legacy_trends_stay_in_instagram_trends_folder() -> None:
    state = TrendCollectionService.merge_state(None)

    assert TrendCollectionService.assigned_collection(state, "legacy-trend") == "trends"


def test_only_admin_manage_routes_can_mutate_folders() -> None:
    source = _source("app/api/v1/trend_collections.py")

    assert '@router.get("")' in source
    assert '@router.get("/{collection_id}/items")' in source
    assert '@router.post("/manage")' in source
    assert '@router.patch("/manage/{collection_id}")' in source
    assert '@router.put("/manage/items/{trend_id}")' in source
    assert "await _inline_admin(session, user_id=user.id)" in source
    assert "AdminPolicy.authorize_action(account, \"social.moderate\", confirmed=True)" in source
    assert '@router.post("")' not in source


def test_catalog_folder_ux_has_photo_and_video_tabs_and_reuses_trend_launcher() -> None:
    source = _source("frontend/mini-app/components/live-trend-rail.tsx")
    admin = _source("frontend/mini-app/components/trend-collection-admin.tsx")

    assert "Выберите, что хотите повторить" in source
    assert "Фото ·" in source
    assert "Видео ·" in source
    assert "/mini-app/trend/?id=" in source
    assert "TrendCollectionAdmin" in source
    assert "＋ Новая папка" in admin
    assert "Разложить шаблоны по папкам" in admin
    assert "Пользователи только выбирают готовое" in admin
