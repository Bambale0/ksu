from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIDEO_JS = ROOT / "app/web/mini_app/roxy-video-controls.js"
VIDEO_CSS = ROOT / "app/web/mini_app/roxy-video-controls.css"
BRAND_JS = ROOT / "app/web/mini_app/roxy-brand.js"


def test_video_controls_cover_every_catalog_video_model() -> None:
    source = VIDEO_JS.read_text(encoding="utf-8")
    for model_id in (
        "wan-2.7-t2v",
        "wan-2.7-i2v",
        "wan-2.7-video-edit",
        "wan-2.7-r2v",
        "seedance-1.5-pro",
        "seedance-2.0",
        "seedance-2.0-fast",
        "seedance-2.0-mini",
        "seedance-2.5",
        "kling-3.0",
        "kling-motion-2.6",
        "kling-motion-3.0",
        "veo-3.1",
        "gemini-omni-video",
        "grok-video-t2v",
        "grok-video-i2v",
        "grok-video-1.5",
        "grok-video-upscale",
        "grok-video-extend",
    ):
        assert f'"{model_id}"' in source


def test_video_controls_expose_documented_structured_modes() -> None:
    source = VIDEO_JS.read_text(encoding="utf-8")
    required_tokens = (
        'segmented("mode", "Качество"',
        'durationControl(3, 15',
        '"multi_prompt"',
        '"kling_elements"',
        '"element_input_urls"',
        '"element_input_audio_urls"',
        '"REFERENCE_2_VIDEO"',
        '"FIRST_AND_LAST_FRAMES_2_VIDEO"',
        '"reference_image"',
        '"reference_video"',
        '"character_ids"',
        '"audio_ids"',
        '"video_list"',
        'payload.parameters.mode = "normal"',
        'payload.parameters.audio_setting = "auto"',
        'payload.parameters.extend_at',
        'payload.parameters.extend_times',
    )
    for token in required_tokens:
        assert token in source


def test_video_controls_intercept_quote_and_submit() -> None:
    source = VIDEO_JS.read_text(encoding="utf-8")
    assert 'url.pathname === "/api/v1/generations"' in source
    assert 'url.pathname === "/api/v1/generations/quote"' in source
    assert "applyExtraParameters(payload)" in source
    assert 'nativeFetch("/api/v1/uploads/kie"' in source


def test_video_controls_are_mounted_by_brand_layer() -> None:
    brand = BRAND_JS.read_text(encoding="utf-8")
    assert 'css: "/mini-app/roxy-video-controls.css?v=1"' in brand
    assert 'js: "/mini-app/roxy-video-controls.js?v=1"' in brand


def test_video_controls_have_mobile_styles() -> None:
    css = VIDEO_CSS.read_text(encoding="utf-8")
    assert ".roxy-video-segments" in css
    assert ".roxy-video-duration-row" in css
    assert ".roxy-video-custom-card" in css
    assert ".roxy-video-quota" in css
    assert "@media (max-width: 640px)" in css
