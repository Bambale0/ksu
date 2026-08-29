from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend" / "mini-app" / "app" / "page.tsx"
RESPONSIVE = ROOT / "frontend" / "mini-app" / "components" / "feed-responsive-layout.tsx"
MODERATION = ROOT / "frontend" / "mini-app" / "components" / "feed-admin-moderation.tsx"


def test_responsive_feed_layout_is_mounted_after_feed_surface() -> None:
    source = PAGE.read_text(encoding="utf-8")
    assert 'import { FeedResponsiveLayout } from "@/components/feed-responsive-layout";' in source
    assert source.index("<TikTokFeedSurface />") < source.index("<FeedResponsiveLayout />")
    assert source.index("<FeedResponsiveLayout />") < source.index("<FeedAdminModeration />")


def test_portrait_feed_repositions_contained_media_and_compacts_action_rail() -> None:
    source = RESPONSIVE.read_text(encoding="utf-8")
    assert "@media (max-width: 560px) and (orientation: portrait)" in source
    assert "object-position: center 34%" in source
    assert "object-position: center 31%" in source
    assert ".tiktok-feed-media > video" in source
    assert "background: transparent" in source
    assert "gap: 7px" in source


def test_admin_toolbar_reserves_space_above_bottom_navigation() -> None:
    responsive = RESPONSIVE.read_text(encoding="utf-8")
    moderation = MODERATION.read_text(encoding="utf-8")
    assert 'root.style.setProperty("--feed-admin-clearance", "58px")' in moderation
    assert "bottom:calc(76px + var(--tg-safe-bottom, 0px))" in moderation
    assert "var(--feed-admin-clearance, 0px)" in responsive
    assert ".tiktok-feed-meta" in responsive
    assert ".tiktok-feed-rail" in responsive
    assert ".tiktok-feed-loader" in responsive
