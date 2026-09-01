from pathlib import Path

from app.services.trend_collections import TrendCollectionService


def _source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_folder_hashtags_are_read_from_title_and_description() -> None:
    collection = {
        "id": "birthday",
        "title": "День рождения #ДР",
        "description": "Поздравления #birthday #праздник",
        "is_active": True,
    }

    assert TrendCollectionService.collection_hashtags(collection) == {
        "др",
        "birthday",
        "праздник",
    }


def test_recipe_tag_routes_to_matching_active_folder() -> None:
    state = TrendCollectionService.merge_state(
        {
            "collections": [
                {
                    "id": "birthday",
                    "title": "День рождения",
                    "description": "Поздравления #др #birthday",
                    "sort_order": 10,
                    "is_active": True,
                },
                {
                    "id": "love",
                    "title": "Love",
                    "description": "Романтика #love",
                    "sort_order": 20,
                    "is_active": True,
                },
            ]
        }
    )

    assert TrendCollectionService.matching_collection(state, ["#ДР", "video"]) == "birthday"
    assert TrendCollectionService.matching_collection(state, ["LOVE"]) == "love"


def test_hashtag_router_skips_live_trends_and_inactive_folders() -> None:
    state = TrendCollectionService.merge_state(
        {
            "collections": [
                {
                    "id": "trends",
                    "title": "Тренды #viral",
                    "description": "live",
                    "sort_order": 0,
                    "is_active": True,
                },
                {
                    "id": "birthday",
                    "title": "День рождения",
                    "description": "#др",
                    "sort_order": 10,
                    "is_active": False,
                },
            ]
        }
    )

    assert TrendCollectionService.matching_collection(state, ["viral"]) is None
    assert TrendCollectionService.matching_collection(state, ["др"]) is None


def test_inline_trend_create_and_update_auto_assign_recipe_tags() -> None:
    source = _source("app/api/v1/trends.py")

    assert source.count("await TrendCollectionService.assign_from_tags(") == 2
    assert 'tags=recipe.get("tags") or []' in source


def test_trend_publish_normalizes_hashtags_without_opening_folder_admin() -> None:
    api_source = _source("frontend/mini-app/lib/trend-admin-api.ts")
    form_source = _source("frontend/mini-app/components/inline-trend-admin.tsx")

    assert "export function normalizeTrendTags" in api_source
    assert "hashtagsFromText(body.title)" in api_source
    assert "hashtagsFromText(body.payload.description)" in api_source
    assert api_source.count("normalizeWriteBody(body)") >= 2
    assert 'split(/[\\s,;]+/u)' in api_source
    assert 'replace(/^#+/, "")' in api_source
    assert "value={draft.tags}" in form_source
    assert "Опубликовать тренд" in form_source
