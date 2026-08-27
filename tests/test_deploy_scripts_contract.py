from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-production.yml"
DOCKERFILE = ROOT / "Dockerfile"


MODULE_RE = re.compile(r"python\s+-m\s+([a-zA-Z_][\w.]+)")
BACKFILL_MODULE_RE = re.compile(
    r"run_backfill\s+\"[^\"]+\"\s+([a-zA-Z_][\w.]+)"
)


def _module_path(module: str) -> Path:
    parts = module.split(".")
    return ROOT.joinpath(*parts).with_suffix(".py")


def _workflow_modules(workflow: str) -> list[str]:
    # Production deploy may execute a literal ``python -m module`` or route the
    # same explicit module through the shared run_backfill wrapper. Keep the
    # concrete module names visible in YAML so packaging/removal regressions are
    # still caught without forbidding a safe helper around command execution.
    return sorted(set(MODULE_RE.findall(workflow)) | set(BACKFILL_MODULE_RE.findall(workflow)))


def test_deploy_python_modules_exist_in_repository() -> None:
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    modules = _workflow_modules(workflow)
    assert modules, "deploy workflow should keep explicit python -m maintenance modules visible"

    missing = [module for module in modules if not _module_path(module).exists()]
    assert missing == []


def test_deploy_scripts_are_packaged_into_runtime_image() -> None:
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    modules = _workflow_modules(workflow)

    if any(module.startswith("scripts.") for module in modules):
        assert (ROOT / "scripts" / "__init__.py").exists()
        assert "COPY scripts ./scripts" in dockerfile
