from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "frontend" / "mini-app"


def test_loader_is_shared_by_boot_and_auth():
    source = (BASE / "components" / "roxy-loading-video.tsx").read_text()
    assert "autoPlay" in source and "muted" in source and "playsInline" in source and "loop" in source
    assert 'preload="metadata"' in source
    for path in ("roxy-app.tsx", "roxy-social-app.tsx", "telegram-auth-boundary.tsx"):
        assert "RoxyLoadingVideo" in (BASE / "components" / path).read_text()


def test_loading_videos_are_bundled_with_correct_formats():
    expected = {
        "roxy-loading-mobile-9x16.webm": b"\x1a\x45\xdf\xa3",
        "roxy-loading-mobile-9x16.mp4": b"",
        "roxy-loading-web-16x9.webm": b"\x1a\x45\xdf\xa3",
        "roxy-loading-web-16x9.mp4": b"",
    }
    for name, prefix in expected.items():
        video = BASE / "public" / "loading" / name
        assert video.is_file() and video.stat().st_size > 100_000, name
        if prefix:
            assert video.read_bytes()[:4] == prefix
        else:
            with video.open("rb") as media:
                assert media.read(12)[4:8] == b"ftyp"