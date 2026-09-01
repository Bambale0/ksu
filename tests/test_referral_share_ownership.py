from pathlib import Path


def _source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_feed_post_and_repeat_links_belong_to_current_sharer() -> None:
    source = _source("app/api/v1/feed.py")
    share_block = source.split('@router.post("/feed/{generation_id}/share")', 1)[1].split(
        '@router.get("/feed/{generation_id}/comments")', 1
    )[0]
    link_block = source.split('@router.get("/feed/{generation_id}/link")', 1)[1].split(
        '@router.get("/profiles/{referral_code}/link")', 1
    )[0]

    assert 'referral_code = str(user.telegram_id)' in share_block
    assert 'FeedService.post_deep_link(generation.id, referral_code)' in share_block
    assert 'FeedService.remix_deep_link(generation.id, referral_code)' in share_block
    assert 'FeedService.share_payload(generation, user.telegram_id)' in share_block
    assert 'referral_code = str(user.telegram_id)' in link_block
    assert 'author.telegram_id' not in share_block
    assert 'author.telegram_id' not in link_block


def test_mini_app_referral_validates_public_source_but_not_source_author() -> None:
    source = _source("app/api/deps.py")
    block = source.split("async def _validated_startapp_inviter", 1)[1].split(
        "async def get_current_user", 1
    )[0]

    assert "FeedService.assert_surface_visible" in block
    assert "TrendService.get_public" in block
    assert "return link.referral_telegram_id" in block
    assert "generation.user_id" not in block
    assert "author.telegram_id != link.referral_telegram_id" not in block
    assert "_existing_inviter" not in source


def test_bot_start_referral_has_same_sharer_semantics_and_supports_trends() -> None:
    source = _source("app/bot/handlers/start.py")
    block = source.split("async def _validated_inviter", 1)[1].split(
        "async def _balances", 1
    )[0]

    assert 'if link.action == "trend":' in block
    assert "TrendService.get_public" in block
    assert "FeedService.assert_surface_visible" in block
    assert "return link.referral_telegram_id" in block
    assert "generation.user_id" not in block
    assert "_existing_inviter" not in source


def test_existing_user_referrer_is_never_reassigned_by_new_share_link() -> None:
    source = _source("app/services/users.py")
    existing_branch = source.split("if user is not None:", 1)[1].split(
        "# A Mini App cold boot", 1
    )[0]

    assert "return user" in existing_branch
    assert "inviter_telegram_id" not in existing_branch
    assert "referrer" not in existing_branch


def test_repeat_composer_can_copy_current_partner_repeat_link() -> None:
    source = _source("frontend/mini-app/app/remix/page.tsx")

    assert "Скопировать ссылку повтора" in source
    assert "/link?kind=remix&surface=" in source
    assert "telegramHeaders(false)" in source
    assert "copyToClipboard(link)" in source


def test_trend_page_can_copy_current_partner_trend_link() -> None:
    source = _source("frontend/mini-app/app/trend/page.tsx")

    assert "Скопировать ссылку тренда" in source
    assert "api.shareTrend(trend.id)" in source
    assert "copyToClipboard(result.copy_link || result.link)" in source
