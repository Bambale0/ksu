from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_user_profile_is_mounted_before_account_cabinet() -> None:
    brand = _read("roxy-brand.js")
    assert '/mini-app/roxy-user-profile.css?v=1' in brand
    assert '/mini-app/roxy-user-profile.js?v=1' in brand
    assert brand.index('/mini-app/roxy-user-profile.js?v=1') < brand.index('/mini-app/roxy-profile-cabinet.js')
    assert brand.index('/mini-app/roxy-user-profile.css?v=1') < brand.index('/mini-app/roxy-design-system.css?v=1')


def test_profile_uses_real_user_and_existing_roxy_backend_contracts() -> None:
    source = _read("roxy-user-profile.js")
    for token in (
        'api("/api/v1/me")',
        'api("/api/v1/me/overview")',
        '/api/v1/generations?limit=${PAGE_SIZE}&status=succeeded',
        '/api/v1/profiles/${encodeURIComponent(state.me.telegram_id)}/feed',
        '/api/v1/profiles/${encodeURIComponent(state.me.telegram_id)}/link',
        '/api/v1/feed/${encodeURIComponent(item.id)}?surface=profile',
        'tg?.initDataUnsafe?.user?.photo_url',
        'X-Telegram-Init-Data',
    ):
        assert token in source


def test_profile_has_private_works_and_publications_as_separate_surfaces() -> None:
    source = _read("roxy-user-profile.js")
    for token in (
        '["works", "grid", "Работы"]',
        '["publications", "feed", "Публикации"]',
        'state.activeTab === "works" ? state.works : state.publications',
        'state.worksCursor',
        'state.publicationsOffset',
        'Показать ещё',
        'Создать первую работу',
    ):
        assert token in source


def test_public_profile_preview_never_renders_public_prompt() -> None:
    source = _read("roxy-user-profile.js")
    assert 'if (surface === "works" && item.prompt && !item.prompt_hidden)' in source
    assert 'surface === "publications" && item.prompt' not in source
    assert 'Prompts are intentionally never exposed from the public/profile publication' in source


def test_profile_gallery_is_mobile_first_and_uses_roxy_tokens() -> None:
    css = _read("roxy-user-profile.css")
    for token in (
        ".roxy-user-profile-hero",
        ".roxy-user-profile-avatar",
        ".roxy-user-profile-stats",
        ".roxy-user-profile-tabs",
        ".roxy-user-profile-grid",
        "grid-template-columns: repeat(3, minmax(0, 1fr))",
        "@media (min-width: 720px)",
        "grid-template-columns: repeat(4, minmax(0, 1fr))",
        "@media (max-width: 430px)",
        "var(--roxy-gradient)",
        "var(--roxy-violet-soft)",
        "prefers-reduced-motion: reduce",
    ):
        assert token in css


def test_old_shell_identity_card_is_hidden_but_account_modules_remain() -> None:
    source = _read("roxy-user-profile.js")
    assert 'profileCard.hidden = true' in source
    assert 'profileCard.setAttribute("aria-hidden", "true")' in source
    assert 'el("h2", "", "Настройки и возможности")' in source
    assert 'profileView.replaceChildren' not in source


def test_author_profile_loads_portfolio_subscriptions_and_share_link() -> None:
    source = _read("roxy-author-profile.js")
    for token in (
        "const PAGE_SIZE = 24",
        '/api/v1/social/profiles/${encodeURIComponent(state.authorId)}',
        '/api/v1/profiles/${encodeURIComponent(profile.referral_code)}/feed',
        '/api/v1/profiles/${encodeURIComponent(profile.referral_code)}/link',
        '/subscribe`, {',
        'profile.subscribed_by_me ? "Отписаться" : "Подписаться"',
        'el("h2", "", "Работы автора")',
        'el("button", "roxy-user-profile-tile")',
    ):
        assert token in source
    assert "item.prompt" not in source


def test_social_profile_exposes_feed_referral_code_without_new_identity_store() -> None:
    source = (ROOT / "app" / "services" / "social.py").read_text(encoding="utf-8")
    assert '"referral_code": str(author.telegram_id)' in source
    assert '"referral_code": str(author.telegram_id) if discoverable else None' in source
    assert '"referral_code": None' in source


def test_work_preview_is_registered_as_nested_telegram_surface() -> None:
    runtime = _read("roxy-mobile-runtime.js")
    assert "#roxyUserWorkPreview" in runtime
    assert 'const profilePreview = document.getElementById("roxyUserWorkPreview")' in runtime
    assert "|| (profilePreview && !profilePreview.hidden)" in runtime
    assert 'document.getElementById("roxyUserWorkPreview")' in runtime
