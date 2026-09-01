from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-production.yml"
DOCKERFILE = ROOT / "Dockerfile"


DIRECT_MODULE_RE = re.compile(r"python\s+-m\s+([a-zA-Z_][\w.]+)")
BACKFILL_MODULE_RE = re.compile(
    r'run_backfill\s+"[^"]+"\s+([a-zA-Z_][\w.]+)'
)


def _module_path(module: str) -> Path:
    parts = module.split(".")
    return ROOT.joinpath(*parts).with_suffix(".py")


def _deploy_modules(workflow: str) -> list[str]:
    modules = set(DIRECT_MODULE_RE.findall(workflow))
    modules.update(BACKFILL_MODULE_RE.findall(workflow))
    return sorted(modules)


def test_deploy_python_modules_exist_in_repository() -> None:
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    modules = _deploy_modules(workflow)
    assert modules, "deploy workflow should keep explicit maintenance modules visible"
    assert "scripts.backfill_reference_static" in modules
    assert "scripts.backfill_feed_static" in modules

    missing = [module for module in modules if not _module_path(module).exists()]
    assert missing == []


def test_deploy_scripts_are_packaged_into_runtime_image() -> None:
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    modules = _deploy_modules(workflow)

    if any(module.startswith("scripts.") for module in modules):
        assert (ROOT / "scripts" / "__init__.py").exists()
        assert "COPY scripts ./scripts" in dockerfile
