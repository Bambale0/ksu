from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_account_center_exposes_backend_user_domains() -> None:
    source = _read("roxy-account-center.js")
    for endpoint in (
        "/api/v1/notifications",
        "/api/v1/notifications/read-all",
        "/api/v1/promocodes/redeem",
        "/api/v1/support/tickets",
        "/api/v1/social/profiles",
        "/api/v1/social/subscriptions",
        "/api/v1/me/preferences",
    ):
        assert endpoint in source
    for action in (
        'method: "POST"',
        'method: "DELETE"',
        'method: "PUT"',
        "/close",
        "/reopen",
        "/messages",
    ):
        assert action in source


def test_account_center_is_mounted_by_main_roxy_runtime() -> None:
    brand = _read("roxy-brand.js")
    assert '/mini-app/roxy-account-center.css' in brand
    assert '/mini-app/roxy-account-center.js' in brand
    assert '/mini-app/roxy-fhd-density.css' in brand
    assert brand.index('/mini-app/roxy-profile-cabinet.js') < brand.index('/mini-app/roxy-account-center.js')
    assert brand.index('/mini-app/roxy-fhd-density.css') < brand.index('/mini-app/roxy-mobile-runtime.css')


def test_full_hd_density_uses_wide_canvas_without_giant_media() -> None:
    css = _read("roxy-fhd-density.css")
    for token in (
        "--roxy-fhd-max: 1760px",
        "@media (min-width: 1440px)",
        "@media (min-width: 1800px)",
        "grid-template-columns: repeat(6",
        "grid-template-columns: repeat(7",
        "--roxy-media-thumb-h: 150px",
        "max-height: var(--roxy-media-thumb-h)",
        "max-height: var(--roxy-media-detail-h)",
        "object-fit: cover",
        "object-fit: contain",
    ):
        assert token in css


def test_mobile_media_stays_compact_and_responsive() -> None:
    css = _read("roxy-fhd-density.css")
    assert "@media (max-width: 720px)" in css
    assert "--roxy-media-thumb-h: 132px" in css
    assert "grid-template-columns: repeat(2" in css
    assert "@media (max-width: 380px)" in css
    assert "--roxy-media-thumb-h: 116px" in css


def test_account_center_keeps_heavy_fetches_profile_scoped() -> None:
    source = _read("roxy-account-center.js")
    assert 'const profile = document.getElementById("profileView")' in source
    assert "if (profile && !profile.hidden) void load();" in source
    assert 'tg?.onEvent?.("activated"' in source
    assert "Promise.all" in source
