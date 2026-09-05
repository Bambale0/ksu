from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "mini-app"

REMOVED_PINTEREST_SERVICE_SURFACES = (
    FRONTEND / "app" / "services" / "page.tsx",
    FRONTEND / "app" / "pinterest-flow" / "page.tsx",
    FRONTEND / "components" / "services-launcher.tsx",
    FRONTEND / "app" / "services.css",
    ROOT / "app" / "api" / "v1" / "pinterest_flow.py",
    ROOT / "app" / "services" / "pinterest_flow.py",
    ROOT / "app" / "services" / "pinterest_flow_contract.py",
    ROOT / "docs" / "pinterest-flow-services.md",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_catalog_uses_feature_hub_not_services_launcher() -> None:
    page = _read(FRONTEND / "app" / "page.tsx")
    layout = _read(FRONTEND / "app" / "layout.tsx")

    assert 'import { CatalogFeatureHub } from "@/components/catalog-feature-hub";' in page
    assert "<CatalogFeatureHub />" in page
    assert "ServicesLauncher" not in page
    assert 'import "./services.css";' not in layout


def test_removed_pinterest_services_stay_removed() -> None:
    for path in REMOVED_PINTEREST_SERVICE_SURFACES:
        assert not path.exists(), f"{path.relative_to(ROOT)} should stay removed"


def test_backend_router_does_not_expose_pinterest_services_namespace() -> None:
    router = _read(ROOT / "app" / "api" / "router.py")

    assert "pinterest_flow" not in router
    assert "/services/pinterest" not in router


def test_catalog_lists_bot_features_not_model_choice_or_legacy_service_promo() -> None:
    hub = _read(FRONTEND / "components" / "catalog-feature-hub.tsx")

    assert "Все фичи ROXY" in hub
    assert "Каталог — это навигация по возможностям бота" in hub
    assert "Выбор конкретной модели остаётся в разделе «Создать»" in hub
    assert "create-image" in hub
    assert "create-video" in hub
    assert "create-audio" in hub
    assert 'id: "pinterest-repeat"' in hub
    assert 'href: "/mini-app/pinterest-repeat/"' in hub
    assert "prompt-image" in hub
    assert "batch" in hub
    assert "/mini-app/batch/" in hub
    assert "/mini-app/prompt-tools/?mode=image" in hub
    assert "/mini-app/prompt-tools/?mode=video" in hub
    assert "Сервисы" not in hub
    assert "/mini-app/services/" not in hub
