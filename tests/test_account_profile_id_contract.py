from pathlib import Path


ACCOUNT_PAGE = Path("frontend/mini-app/app/account/page.tsx")
ACCOUNT_PROFILE_SERVICE = Path("app/services/account_profile.py")


def test_account_overview_exposes_internal_account_id() -> None:
    source = ACCOUNT_PROFILE_SERVICE.read_text(encoding="utf-8")

    assert '"account": {' in source
    assert '"id": str(user.id)' in source


def test_mini_app_profile_displays_internal_account_id() -> None:
    source = ACCOUNT_PAGE.read_text(encoding="utf-8")

    assert "account: { id: string;" in source
    assert 'aria-label="ID аккаунта"' in source
    assert '<span className="kicker">ID аккаунта</span>' in source
    assert "{overview.account.id}" in source
