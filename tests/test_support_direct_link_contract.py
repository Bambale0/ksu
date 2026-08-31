from app.bot.support_links import direct_support_handle, normalize_direct_support_url
from app.core.config import Settings


def test_support_contact_is_opt_in_by_default() -> None:
    assert Settings.model_fields["support_telegram_url"].default == ""
    assert normalize_direct_support_url("") is None


def test_support_contact_accepts_current_operator() -> None:
    assert normalize_direct_support_url("https://t.me/korkinaxenia") == "https://t.me/korkinaxenia"
    assert normalize_direct_support_url("https://t.me/korkinaxenia/") == "https://t.me/korkinaxenia"
    assert normalize_direct_support_url("tg://resolve?domain=korkinaxenia") == "https://t.me/korkinaxenia"
    assert direct_support_handle("https://t.me/korkinaxenia") == "@korkinaxenia"


def test_support_contact_rejects_malformed_telegram_links() -> None:
    assert normalize_direct_support_url("https://t.me/") is None
    assert normalize_direct_support_url("https://t.me/roxy_support/app?startapp=ref_1") is None
    assert normalize_direct_support_url("tg://resolve?domain=") is None
    assert normalize_direct_support_url("https://example.com/support") is None


def test_support_contact_accepts_explicit_telegram_username() -> None:
    assert normalize_direct_support_url(" https://t.me/roxy_support/ ") == "https://t.me/roxy_support"
    assert normalize_direct_support_url("tg://resolve?domain=roxy_support") == "https://t.me/roxy_support"
    assert direct_support_handle("https://t.me/roxy_support") == "@roxy_support"


def test_support_contact_allows_invite_link_but_does_not_render_it_as_mention() -> None:
    invite = "https://t.me/+abcdEFGH123"
    assert normalize_direct_support_url(invite) == invite
    assert direct_support_handle(invite) is None
