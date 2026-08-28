from pathlib import Path

from app.core.config import settings
from app.services.partner import PartnerService


def test_me_owns_profile_share_link_contract() -> None:
    source = Path("app/api/v1/me.py").read_text()
    assert "\"profile_link\": PartnerService.profile_link(user.telegram_id)" in source


def test_profile_share_does_not_depend_on_partner_stats() -> None:
    source = Path("frontend/mini-app/components/roxy-social-app.tsx").read_text()
    assert "if (me?.profile_link) return me.profile_link;" in source
    assert 'aria-label="Поделиться профилем"' in source


def test_profile_link_is_direct_main_mini_app(monkeypatch) -> None:
    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")
    assert PartnerService.profile_link(123456) == (
        "https://t.me/RoxyExampleBot?startapp=profile_123456_ref_123456"
    )
