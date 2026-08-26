from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_batch_generation_router_has_one_canonical_mount() -> None:
    main_source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    api_router_source = (ROOT / "app/api/router.py").read_text(encoding="utf-8")

    assert main_source.count('app.include_router(batch_router, prefix="/api/v1")') == 1
    assert "api_router.include_router(batches.router)" not in api_router_source


def test_customer_parity_pages_cover_backend_capabilities() -> None:
    root = ROOT / "frontend/mini-app"
    expected_pages = {
        "account": "/api/v1/me/overview",
        "notifications": "/api/v1/notifications",
        "support": "/api/v1/support/tickets",
        "settings": "/api/v1/me/preferences",
        "promocodes": "/api/v1/promocodes/redeem",
        "partner-wallet": "/api/v1/referrals/wallet-transfers",
        "subscriptions": "/api/v1/social/subscriptions/feed",
        "history-manager": "/api/v1/generation-history/hidden",
        "actions": "/api/v1/generations/",
        "creator-partnership": "/api/v1/creator-partnership",
        "presets": "/api/v1/presets",
        "payments": "/api/v1/payments/card/packages",
        "downloads": "download_url",
    }

    for page, api_marker in expected_pages.items():
        source = (root / "app" / page / "page.tsx").read_text(encoding="utf-8")
        assert api_marker in source, f"{page} must consume {api_marker}"


def test_main_mini_app_exposes_parity_surfaces() -> None:
    root = ROOT / "frontend/mini-app"
    page = (root / "app/page.tsx").read_text(encoding="utf-8")
    profile_hub = (root / "components/customer-parity-hub.tsx").read_text(encoding="utf-8")
    catalog_hub = (root / "components/catalog-parity-features.tsx").read_text(encoding="utf-8")

    assert "<CustomerParityHub />" in page
    assert "<CatalogParityFeatures />" in page

    for path in (
        "/mini-app/account/",
        "/mini-app/payments/",
        "/mini-app/notifications/",
        "/mini-app/support/",
        "/mini-app/settings/",
        "/mini-app/subscriptions/",
        "/mini-app/presets/",
        "/mini-app/downloads/",
        "/mini-app/promocodes/",
        "/mini-app/partner-wallet/",
        "/mini-app/creator-partnership/",
        "/mini-app/actions/",
        "/mini-app/history-manager/",
    ):
        assert path in profile_hub or path in catalog_hub

    assert "/api/v1/discovery/home" in profile_hub
    assert "data-cms-discovery" in profile_hub
