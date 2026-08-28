from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "frontend" / "mini-app"


def test_feed_repeat_routes_through_reference_composer_before_launch() -> None:
    api = (MINI / "lib" / "api.ts").read_text(encoding="utf-8")
    composer = (MINI / "app" / "remix" / "page.tsx").read_text(encoding="utf-8")
    feed_api = (ROOT / "app" / "api" / "v1" / "feed.py").read_text(encoding="utf-8")
    staged_api = (ROOT / "app" / "api" / "v1" / "feed_remix.py").read_text(encoding="utf-8")

    assert "/mini-app/remix/?source=" in api
    assert "sessionStorage" not in api
    assert "window.location.assign(target)" in api
    assert "/remix/prepare" in api
    assert "launchRemix" in api

    assert "api.prepareRemix(query.source, query.surface)" in composer
    assert "Референсы исходной публикации не копируются" in composer
    assert "reference_ids: references.map" in composer
    assert "confirm_own_references: true" in composer
    assert "api.upload(file)" in composer
    assert "draft.prompt_hidden" in composer

    assert "FeedService.remix(" not in feed_api
    assert "HTTP_409_CONFLICT" in feed_api
    assert '/feed/{generation_id}/remix/prepare' in staged_api
    assert '/feed/{generation_id}/remix/launch' in staged_api
