from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_roxy_release.py"


def _load_release_gate():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("check_roxy_release", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_roxy_release_acceptance_contract_is_green() -> None:
    gate = _load_release_gate()
    assert gate.validate() == []


def test_release_viewport_matrix_covers_mobile_desktop_and_fhd() -> None:
    gate = _load_release_gate()
    assert gate.TARGET_VIEWPORTS == (
        (360, 800),
        (390, 844),
        (430, 932),
        (1366, 768),
        (1920, 1080),
    )
