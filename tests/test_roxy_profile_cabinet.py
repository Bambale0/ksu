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
        "Партнёры ROXY",
        "Настройки",
        "Баланс ROX",
        "Заработок партнёра",
        'window.RoxyCustomerNavigation?.open?.(route)',
        'api("/api/v1/me/overview")',
        'api("/api/v1/referrals/stats")',
        'scrollTo("partnerPreview")',
        'scrollTo("profileTools")',
    ):
        assert token in source
    assert "Бонусные ROX" not in source
    assert "Выводимые ROX" not in source


def test_creator_partnership_is_explicitly_separate_from_referral_economy() -> None:
    source = _read("roxy-profile-cabinet.js")
    for token in (
        "Creator-партнёрство",
        "не реферальные 30% / 5%",
        "не являются реферальным заработком в рублях",
        "Партнёры ROXY",
        "Заработок 30% / 5%",
        "ROX на контент",
        "условия и ежемесячный ROX-лимит согласуются индивидуально",
    ):
        assert token in source
    assert "ReferralReward" not in source
    assert "/withdraw" not in source
    assert "/payments" not in source


def test_creator_partnership_uses_real_application_and_status_lifecycle() -> None:
    source = _read("roxy-profile-cabinet.js")
    for token in (
        'api("/api/v1/creator-partnership")',
        'api("/api/v1/creator-partnership/applications", {',
        'method: "POST"',
        '"Idempotency-Key": crypto.randomUUID()',
        'form.addEventListener("submit", submitCreatorApplication)',
        '"Название канала / проекта"',
        '"Подписчики"',
        '"Средние просмотры"',
        '"Формат сотрудничества"',
        '"На рассмотрении"',
        '"Одобрено"',
        '"Отклонено"',
        '"Начисления по соглашению"',
    ):
        assert token in source
    assert 'document.getElementById("supportComposeForm")' not in source
    assert 'topic.value = "Creator-партнёрство ROXY"' not in source


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
