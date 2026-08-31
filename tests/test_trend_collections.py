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
    assert '@router.put("/manage/items/{trend_id}")' in source
    assert "await _inline_admin(session, user_id=user.id)" in source
    assert "AdminPolicy.authorize_action(account, \"social.moderate\", confirmed=True)" in source
    assert '@router.post("")' not in source


def test_home_folder_ux_has_category_grid_photo_video_tabs_and_trend_launcher() -> None:
    source = _source("frontend/mini-app/components/home-trend-folders.tsx")
    admin = _source("frontend/mini-app/components/trend-collection-admin.tsx")
    page = _source("frontend/mini-app/app/page.tsx")

    assert "Папки трендов" in source
    assert 'folder.system_key !== "trends"' in source
    assert "Фото ·" in source
    assert "Видео ·" in source
    assert "/mini-app/trend/?id=" in source
    assert "TrendCollectionAdmin" in source
    assert "＋ Новая папка" in admin
    assert "Разложить шаблоны по папкам" in admin
    assert "HomeTrendFolders" in page


def test_top_live_trends_are_real_api_cards_not_legacy_model_sections() -> None:
    source = _source("frontend/mini-app/components/live-trend-rail.tsx")
    page = _source("frontend/mini-app/app/page.tsx")

    assert "roxy-home-live-trends" in source
    assert 'window.location.assign(`/mini-app/trend/?id=${encodeURIComponent(trend.id)}`)' in source
    assert "HomeTrendOrder" not in page
