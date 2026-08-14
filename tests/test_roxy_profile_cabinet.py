from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_profile_cabinet_consolidates_customer_account_actions() -> None:
    source = _read("roxy-profile-cabinet.js")
    for token in (
        "Мои ROX",
        "История",
        "Реферальная программа",
        "Настройки",
        'window.RoxyCustomerNavigation?.open?.(route)',
        'api("/api/v1/me/overview")',
        'api("/api/v1/referrals/stats")',
        'scrollTo("partnerPreview")',
        'scrollTo("profileTools")',
    ):
        assert token in source


def test_creator_partnership_is_explicitly_separate_from_referral_economy() -> None:
    source = _read("roxy-profile-cabinet.js")
    for token in (
        "Creator-партнёрство",
        "не реферальные 30% / 5%",
        "ежемесячные начисления ROX",
        "Персональные условия согласуются вручную",
        "Автоматическая реферальная программа",
        "Рефералы 30% / 5%",
    ):
        assert token in source
    assert "ReferralReward" not in source
    assert "/withdraw" not in source
    assert "/payments" not in source


def test_creator_contact_uses_existing_support_flow_until_partnership_epic() -> None:
    source = _read("roxy-profile-cabinet.js")
    assert 'document.getElementById("supportComposeForm")' in source
    assert 'topic.value = "Creator-партнёрство ROXY"' in source
    assert "Канал / аудитория / формат сотрудничества" in source
    assert "fetch(" not in source


def test_profile_cabinet_hides_technical_account_overview_from_customer_surface() -> None:
    css = _read("roxy-profile-cabinet.css")
    source = _read("roxy-profile-cabinet.js")
    assert ".roxy-profile-cabinet-ready .account-overview-card" in css
    assert "display: none !important" in css
    assert "Telegram ID" not in source
    assert "rub_accounting_equivalent" not in source
    assert "кредитов" not in source.lower()


def test_roxy_brand_mounts_profile_cabinet_layer() -> None:
    brand = _read("roxy-brand.js")
    assert '/mini-app/roxy-profile-cabinet.css' in brand
    assert '/mini-app/roxy-profile-cabinet.js' in brand
