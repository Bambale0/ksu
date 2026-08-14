import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _read(name: str) -> str:
    return (MINI / name).read_text(encoding="utf-8")


def test_embedded_batch_javascript_is_syntactically_valid() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    subprocess.run(
        [node, "--check", str(MINI / "roxy-batch-embedded.js")],
        check=True,
        capture_output=True,
        text=True,
    )


def test_batch_is_embedded_without_duplicating_backend_client() -> None:
    source = _read("roxy-batch-embedded.js")
    for token in (
        'dialog.id = "roxyEmbeddedBatch"',
        'script.src = "/mini-app/bulk.js"',
        'link.href = "/mini-app/batch.css"',
        'history.pushState',
        'history.back()',
        'tg?.BackButton?.onClick?.(onBackButton)',
        'window.setTimeout(() => closeBatch({ historyBack: true }), 0)',
        'a[href="/mini-app/batch.html"]',
        'window.RoxyBatchEmbedded = Object.freeze',
        'files.id = "batchFiles"',
        'model.id = "batchModel"',
        'prompt.id = "batchPrompt"',
        'start.id = "batchStart"',
        'progress.id = "batchProgress"',
    ):
        assert token in source
    # Existing bulk.js remains the only API client for this domain.
    assert "/api/v1/batch-generations" not in source
    assert "fetch(" not in source
    assert "MutationObserver" not in source


def test_parity_navigation_opens_embedded_batch_first() -> None:
    source = _read("roxy-parity-navigation.js")
    assert '/mini-app/roxy-batch-embedded.css' in source
    assert '/mini-app/roxy-batch-embedded.js' in source
    assert "window.RoxyBatchEmbedded?.open" in source
    assert "window.RoxyBatchEmbedded.open()" in source
    assert 'card("▦", "Batch", "Пакетные генерации", () => openBatch())' in source
    # Legacy standalone route is retained only as a bounded fallback.
    assert 'openMiniPage(`${MINI_ROOT}batch.html`)' in source


def test_embedded_batch_is_compact_on_fhd_and_fullscreen_on_mobile() -> None:
    css = _read("roxy-batch-embedded.css")
    for token in (
        "max-width: 1180px",
        "height: min(900px, calc(100dvh - 28px))",
        "grid-template-columns: repeat(auto-fill, minmax(68px, 82px))",
        "width: 82px",
        "@media (max-width: 620px)",
        "width: 100vw",
        "height: 100dvh",
        "env(safe-area-inset-bottom, 0px)",
    ):
        assert token in css


def test_existing_batch_runtime_remains_server_authoritative() -> None:
    source = _read("bulk.js")
    for endpoint in (
        "/api/v1/batch-generations/quote",
        "/api/v1/batch-generations/",
        "/api/v1/generations/models",
        "/api/v1/uploads/kie",
    ):
        assert endpoint in source
    assert 'credentials: "same-origin"' in source
    assert 'headers["X-Telegram-Init-Data"] = tg.initData' in source
