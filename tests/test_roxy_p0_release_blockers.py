from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_customer_navigation_is_single_router_without_menu_replacement_or_body_observer() -> None:
    source = _read("app/web/mini_app/roxy-customer-navigation.js")
    assert "replaceChildren" not in source
    assert "MutationObserver" not in source
    assert "data-studio-route" in source
    assert "data-roxy-customer-route" in source
    assert "stopImmediatePropagation" in source
    assert 'window.dispatchEvent(new CustomEvent("roxy:route-changed"' in source


def test_music_runtime_has_no_subtree_mutation_observer() -> None:
    source = _read("app/web/mini_app/roxy-music.js")
    assert "MutationObserver" not in source
    assert "subtree: true" not in source
    assert 'window.addEventListener("roxy:route-changed", scheduleApply)' in source
    assert 'window.addEventListener("roxy:shell-route-changed", scheduleApply)' in source
    assert 'document.addEventListener("load", handleRenderedMedia, true)' in source
    assert 'document.addEventListener("error", handleRenderedMedia, true)' in source


def test_economy_runtime_does_not_watch_the_whole_body_subtree() -> None:
    source = _read("app/web/mini_app/roxy-economy.js")
    assert 'observeRoot("roxyWalletView"' in source
    assert 'observeRoot("studioInsufficientDialog"' in source
    assert ".observe(document.body" not in source


def test_hidden_history_is_persisted_and_restorable_after_reload() -> None:
    api = _read("app/api/v1/generation_history.py")
    generation_api = _read("app/api/v1/generations.py")
    ui = _read("app/web/mini_app/roxy-history-management.js")
    assert '"/hidden"' in api
    assert "GenerationHistoryState" in api
    assert '"/{generation_id}/history"' in generation_api
    assert 'method: "PUT"' in ui
    assert "Скрытые" in ui
    assert "Вернуть" in ui
    assert "/api/v1/generation-history/hidden" in ui


def test_preset_edit_update_ui_is_present() -> None:
    api = _read("app/api/v1/reference_presets.py")
    ui = _read("app/web/mini_app/roxy-preset-editor.js")
    assert 'router.put("/presets/{preset_id}"' in api
    assert "Редактировать" in ui
    assert 'method: "PUT"' in ui
    assert "/api/v1/reference-presets/presets/" in ui


def test_feed_hides_repeat_when_backend_disallows_prompt_actions() -> None:
    source = _read("app/web/mini_app/feed.js")
    assert "prompt_actions_allowed !== false" in source
    assert "Повторить" in source
