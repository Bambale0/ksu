from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_prune_workflow_runs_only_from_trusted_main_and_has_minimal_write_scope() -> None:
    workflow = _read(".github/workflows/prune-merged-branches.yml")

    assert "push:" in workflow
    assert "- main" in workflow
    assert "ref: main" in workflow
    assert "contents: write" in workflow
    assert "pull-requests: read" in workflow
    assert "bash scripts/prune_merged_branches.sh" in workflow


def test_prune_script_preserves_unmerged_reused_and_protected_branches() -> None:
    script = _read("scripts/prune_merged_branches.sh")

    assert "pulls?state=open" in script
    assert "pulls?state=closed" in script
    assert ".merged_at != null" in script
    assert 'main|master|develop|development|staging|production|prod|release|release/*' in script
    assert 'grep -Fxq "$branch" "$open_heads"' in script
    assert '[[ "$current_sha" != "$merged_sha" ]]' in script
    assert 'git/refs/heads/${branch}' in script
    assert "-X DELETE" in script
