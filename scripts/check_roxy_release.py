from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "mini-app"
GENERATED = ROOT / "app" / "web" / "mini_app"

TARGET_VIEWPORTS = (
    (360, 800),
    (390, 844),
    (430, 932),
    (1366, 768),
    (1920, 1080),
)

REQUIRED_SOURCE = (
    "package.json",
    "next.config.mjs",
    "tsconfig.json",
    "app/layout.tsx",
    "app/page.tsx",
    "app/globals.css",
    "components/roxy-app.tsx",
    "components/icons.tsx",
    "lib/api.ts",
    "lib/telegram.ts",
    "lib/types.ts",
)

FORBIDDEN_LEGACY = (
    "CREATOR ECONOMY",
    "Creator economy",
    "Как заработать ROX",
    "Создал → опубликовал → заработал",
    "roxyEarnSection",
    "roxyApprovedHero",
    "studio-shell",
    "shell-integration",
    "roxy-approved-home",
    "roxy-theme-compat",
)


def read(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def validate() -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_SOURCE:
        path = FRONTEND / relative
        if not path.is_file() or path.stat().st_size < 40:
            errors.append(f"missing-source:{relative}")

    generated_files = sorted(path.name for path in GENERATED.iterdir() if path.is_file())
    if generated_files != ["README.md", "release.json"]:
        errors.append("generated-directory-must-not-contain-source:" + ",".join(generated_files))
    else:
        try:
            release = json.loads((GENERATED / "release.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append("generated-release-json")
        else:
            if sorted(release) != ["sha"] or not isinstance(release["sha"], str):
                errors.append("generated-release-json")

    if errors:
        return errors

    package = json.loads(read("package.json"))
    if package.get("dependencies", {}).get("next") != "16.3.1":
        errors.append("next-version")
    if package.get("dependencies", {}).get("react") != "19.2.8":
        errors.append("react-version")
    if package.get("dependencies", {}).get("react-dom") != "19.2.8":
        errors.append("react-dom-version")

    config = read("next.config.mjs")
    for token in ('output: "export"', 'basePath: "/mini-app"', "trailingSlash: true"):
        if token not in config:
            errors.append(f"next-config:{token}")

    app = read("components/roxy-app.tsx")
    css = read("app/globals.css")
    api = read("lib/api.ts")
    telegram = read("lib/telegram.ts")

    for legacy in FORBIDDEN_LEGACY:
        if legacy in app:
            errors.append(f"legacy-copy:{legacy}")

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
        "if (booting) return <Splash />",
        "visibleFields(selected, draft)",
        "model.ui_schema?.fields",
    ):
        if token not in app:
            errors.append(f"react-app:{token}")
    if "Лента" in app:
        errors.append("legacy-primary-nav-label")

    for endpoint in (
        "/api/v1/me",
        "/api/v1/generations/models",
        "/api/v1/generations/quote",
        "/api/v1/generations",
        "/api/v1/uploads/kie",
        "/api/v1/feed",
        "/api/v1/payments",
    ):
        if endpoint not in api:
            errors.append(f"api:{endpoint}")
    if "prompt_visible: false" not in api or "references_visible: false" not in api:
        errors.append("public-prompt-privacy")

    for token in ("#0b0b10", "#9b5cff", "#ff5fb7", "#ffffff", "#a6a6b3"):
        if token not in css.lower():
            errors.append(f"palette:{token}")
    for token in ("--tg-safe-bottom", "min-height: 44px", "prefers-reduced-motion: reduce", ".splash"):
        if token not in css:
            errors.append(f"design:{token}")

    for token in (
        'setHeaderColor?.("#0B0B10")',
        'setBackgroundColor?.("#0B0B10")',
        'setBottomBarColor?.("#0B0B10")',
        "contentSafeAreaInset",
        "BackButton",
    ):
        if token not in telegram:
            errors.append(f"telegram:{token}")

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for token in (
        "FROM node:22-alpine AS miniapp",
        "RUN npm run build",
        "rm -rf ./app/web/mini_app",
        "COPY --from=miniapp /src/frontend/mini-app/out ./app/web/mini_app",
    ):
        if token not in dockerfile:
            errors.append(f"docker:{token}")

    return errors


def main() -> int:
    errors = validate()
    print("ROXY Next.js release target viewports:")
    for width, height in TARGET_VIEWPORTS:
        print(f"  - {width}x{height}")
    if errors:
        print("ROXY release gate FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("ROXY release gate PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
