from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
LOCK_TEXT = (ROOT / "constraints/runtime.txt").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(requirement: str) -> str:
    return _normalize(re.split(r"[\[<>=!~; ]", requirement, maxsplit=1)[0])


def _locked_versions() -> dict[str, str]:
    locked: dict[str, str] = {}
    for raw in LOCK_TEXT.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^=\s]+)", line)
        assert match is not None, f"Runtime constraint must be exact: {line}"
        name = _normalize(match.group(1))
        assert name not in locked, f"Duplicate runtime constraint: {name}"
        locked[name] = match.group(2)
    return locked


def test_every_direct_runtime_dependency_is_exactly_constrained() -> None:
    locked = _locked_versions()
    direct = {
        _requirement_name(requirement)
        for requirement in PYPROJECT["project"]["dependencies"]
    }
    missing = sorted(direct - locked.keys())
    assert not missing, f"Direct runtime dependencies missing from constraints: {missing}"


def test_runtime_lock_captures_transitive_closure_not_only_direct_requirements() -> None:
    locked = _locked_versions()
    direct_count = len(PYPROJECT["project"]["dependencies"])
    assert len(locked) > direct_count * 2
    for transitive in (
        "starlette",
        "pydantic-core",
        "botocore",
        "opentelemetry-proto",
        "aiohttp",
    ):
        assert transitive in locked


def test_production_docker_install_enforces_runtime_lock_and_dependency_check() -> None:
    assert "COPY constraints/runtime.txt ./constraints/runtime.txt" in DOCKERFILE
    assert "pip install --no-cache-dir -c constraints/runtime.txt ." in DOCKERFILE
    assert "&& pip check" in DOCKERFILE
