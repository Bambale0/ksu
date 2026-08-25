from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "mini-app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_root_mini_app_exposes_services_launcher() -> None:
    page = _read(FRONTEND / "app" / "page.tsx")
    assert 'import { ServicesLauncher } from "@/components/services-launcher";' in page
    assert "<ServicesLauncher />" in page


def test_services_surface_opens_pinterest_flow() -> None:
    services = _read(FRONTEND / "app" / "services" / "page.tsx")
    launcher = _read(FRONTEND / "components" / "services-launcher.tsx")
    runner = _read(FRONTEND / "app" / "pinterest-flow" / "page.tsx")
    layout = _read(FRONTEND / "app" / "layout.tsx")

    assert 'window.location.assign("/mini-app/services/")' in launcher
    assert 'request<ServicesResponse>("/api/v1/services/pinterest")' in services
    assert "/mini-app/pinterest-flow/?id=" in services
    assert "/api/v1/services/pinterest/${encodeURIComponent(serviceId)}/run" in runner
    assert 'import "./services.css";' in layout


def test_backend_registers_dedicated_pinterest_service_router() -> None:
    router = _read(ROOT / "app" / "api" / "router.py")
    api = _read(ROOT / "app" / "api" / "v1" / "pinterest_flow.py")
    trends_api = _read(ROOT / "app" / "api" / "v1" / "trends.py")

    assert "pinterest_flow," in router
    assert "api_router.include_router(pinterest_flow.router)" in router
    assert 'APIRouter(prefix="/services/pinterest"' in api
    assert "Pinterest Flow is available in Services" in trends_api
