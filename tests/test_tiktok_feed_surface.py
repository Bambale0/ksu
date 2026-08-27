from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "frontend" / "mini-app"
COMPONENT = MINI / "components" / "tiktok-feed-surface.tsx"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_main_app_mounts_real_tiktok_feed_instead_of_pinterest_guard() -> None:
    page = _read(MINI / "app" / "page.tsx")

    assert 'import { TikTokFeedSurface } from "@/components/tiktok-feed-surface"' in page
    assert "<TikTokFeedSurface />" in page
    assert "SingleFeedSurfaceGuard" not in page


def test_tiktok_feed_is_fullscreen_vertical_snap_surface() -> None:
    source = _read(COMPONENT)

    for token in (
        'className="tiktok-feed-surface"',
        'className="tiktok-feed-scroll"',
        "scroll-snap-type: y mandatory",
        "scroll-snap-align: start",
        "scroll-snap-stop: always",
        "IntersectionObserver",
        "videoRefs.current",
        "void video.play()",
        'loop\n                preload=',
        "onDoubleClick={() => void toggleLike(card, true)}",
    ):
        assert token in source, token


def test_tiktok_feed_keeps_social_actions_and_following_feed() -> None:
    source = _read(COMPONENT)

    for token in (
        '"for-you"',
        '"following"',
        "/api/v1/social/subscriptions/feed",
        "/api/v1/social/profiles/",
        "/subscribe",
        "api.like(",
        "api.unlike(",
        "api.comments(",
        "api.addComment(",
        "api.share(",
        "api.remix(",
        "api.removePublication(",
        "api.profileFeed(",
        "copyToClipboard",
        "openTelegramShare",
        "reference_images",
        "reference_videos",
        "feed_blurred",
    ):
        assert token in source, token


def test_tiktok_feed_preserves_visibility_and_privacy_contracts() -> None:
    source = _read(COMPONENT)

    assert "card.prompt && !card.prompt_hidden" in source
    assert "!detailsCard.references_hidden" in source
    assert "card.prompt_actions_allowed !== false" in source
    assert "detailsCard.prompt_actions_allowed !== false" in source
    assert "card.is_mine" in source
    assert "detailsCard.is_mine" in source
    assert "feed_interactions_enabled" not in source or "FeedCard" in source
