from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "mini-app"
GENERATED = ROOT / "app" / "web" / "mini_app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_customer_app_has_one_next_react_source() -> None:
    package = json.loads(_read(FRONTEND / "package.json"))
    assert package["dependencies"]["next"] == "16.3.1"
    assert package["dependencies"]["react"] == "19.2.8"
    assert package["dependencies"]["react-dom"] == "19.2.8"
    assert package["scripts"]["build"] == "next build"
    assert package["scripts"]["typecheck"] == "next typegen && tsc --noEmit"

    config = _read(FRONTEND / "next.config.mjs")
    assert 'output: "export"' in config
    assert 'basePath: "/mini-app"' in config
    assert "trailingSlash: true" in config


def test_generated_static_directory_contains_no_customer_source() -> None:
    files = sorted(path.name for path in GENERATED.iterdir() if path.is_file())
    assert set(files) <= {"README.md", "release.json"}
    assert "README.md" in files
    readme = _read(GENERATED / "README.md")
    assert "frontend/mini-app" in readme
    assert "Do not add customer UI source files" in readme
    if "release.json" in files:
        release = json.loads(_read(GENERATED / "release.json"))
        assert sorted(release) == ["sha"]
        assert isinstance(release["sha"], str)


def test_docker_build_replaces_generated_directory_with_next_export() -> None:
    dockerfile = _read(ROOT / "Dockerfile")
    for token in (
        "FROM node:22-alpine AS miniapp",
        "COPY frontend/mini-app/package.json frontend/mini-app/package-lock.json ./",
        "RUN npm ci --no-audit --no-fund",
        "RUN npm run build",
        "rm -rf ./app/web/mini_app",
        "COPY --from=miniapp /src/frontend/mini-app/out ./app/web/mini_app",
        "ARG MINI_APP_RELEASE_SHA=unknown",
        'RUN printf \'{"sha":"%s"}\\n\' "${MINI_APP_RELEASE_SHA}" > ./app/web/mini_app/release.json',
    ):
        assert token in dockerfile


def test_react_app_owns_all_primary_customer_routes() -> None:
    app = _read(FRONTEND / "components" / "roxy-app.tsx")
    for token in (
        '"home"',
        '"catalog"',
        '"create"',
        '"history"',
        '"profile"',
        "Главная",
        "Каталог",
        "Создать",
        "История",
        "Профиль",
        "Работы",
        "Публикации",
    ):
        assert token in app
    assert "Лента" not in app


def test_catalog_is_not_replaced_by_a_second_feed_overlay() -> None:
    layout = _read(FRONTEND / "app" / "layout.tsx")
    page = _read(FRONTEND / "app" / "page.tsx")
    guard = _read(FRONTEND / "components" / "single-feed-surface-guard.tsx")
    public_dir = FRONTEND / "public"
    styles_dir = FRONTEND / "app"

    assert "feed-social-polish.js" not in layout
    assert "feed-social.css" not in layout
    assert "feed-social-interactions.css" not in layout
    assert not (public_dir / "feed-social-polish.js").exists()
    assert not (styles_dir / "feed-social.css").exists()
    assert not (styles_dir / "feed-social-interactions.css").exists()
    assert "<SingleFeedSurfaceGuard />" in page
    assert 'currentRoute() === "feed"' in guard
    assert 'replaceRoute("catalog")' in guard
    assert 'feedButtons.length > 1' in guard
    assert 'setButtonLabel(duplicate, "Каталог")' in guard


def test_first_frame_is_new_react_splash_and_legacy_home_is_absent() -> None:
    app = _read(FRONTEND / "components" / "roxy-app.tsx")
    css = _read(FRONTEND / "app" / "globals.css")
    assert "if (booting) return <Splash />" in app
    assert 'className="splash"' in app
    assert ".splash" in css
    for legacy in (
        "CREATOR ECONOMY",
        "Creator economy",
        "Как заработать ROX",
        "Создал → опубликовал → заработал",
        "roxyEarnSection",
        "roxyApprovedHero",
        "studio-shell",
        "shell-integration",
    ):
        assert legacy not in app


def test_generation_ui_is_backend_schema_driven() -> None:
    app = _read(FRONTEND / "components" / "roxy-app.tsx")
    api = _read(FRONTEND / "lib" / "api.ts")
    types = _read(FRONTEND / "lib" / "types.ts")
    assert '"/api/v1/generations/models"' in api
    assert '"/api/v1/generations/quote"' in api
    assert '"/api/v1/generations"' in api
    assert '"/api/v1/uploads/kie"' in api
    assert "model.ui_schema?.fields" in app
    assert "visibleFields(selected, draft)" in app
    assert "ui_schema?: UiSchema" in types
    assert "localStorage.setItem(MODEL_KEY" in app
    assert "localStorage.setItem(DRAFTS_KEY" in app


def test_generation_ui_uses_family_variant_picker() -> None:
    app = _read(FRONTEND / "components" / "roxy-app.tsx")
    css = _read(FRONTEND / "app" / "globals.css")
    types = _read(FRONTEND / "lib" / "types.ts")
    assert "GenerationModelFamily" in types
    assert "families?: GenerationModelFamily[]" in _read(FRONTEND / "lib" / "api.ts")
    assert "<FamilyVariantSheet" in app
    assert "family-grid" in app
    assert 'const MEDIA_FILTER_KEY = "ksu-selected-media"' in app
    assert "onCreate(\"image\")" in app
    assert "visibleFamilies.map((family)" in app
    assert "setFamilySheet(family)" in app
    assert "variant-list" in css
    assert "family-tabs" in css
    assert "<select className=\"control\" value={selected.id}" not in app


def test_public_profile_never_exposes_prompt() -> None:
    app = _read(FRONTEND / "components" / "roxy-app.tsx")
    api = _read(FRONTEND / "lib" / "api.ts")
    assert 'prompt_visible: false' in api
    assert 'references_visible: false' in api
    assert 'surface === "private" && item.prompt' in app
    assert "profilePublications" in app
    assert "profileWorks" in app


def test_mini_app_resets_pre_duration_select_drafts_once() -> None:
    layout = _read(FRONTEND / "app" / "layout.tsx")
    assert 'id="roxy-draft-schema-reset"' in layout
    assert 'roxy.next.generation-drafts.schema' in layout
    assert 'currentVersion = "4"' in layout
    assert 'removeItem("roxy.next.generation-drafts.v3")' in layout


def test_design_tokens_match_current_roxy_system() -> None:
    css = _read(FRONTEND / "app" / "globals.css").lower()
    for token in ("#0b0b10", "#9b5cff", "#ff5fb7", "#ffffff", "#a6a6b3"):
        assert token in css
    assert "--tg-safe-bottom" in css
    assert "min-height: 44px" in css
    assert "prefers-reduced-motion: reduce" in css
