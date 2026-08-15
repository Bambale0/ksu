from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-production.yml"
DOC = ROOT / "docs" / "GITHUB_PRODUCTION_DEPLOY.md"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_production_deploy_waits_for_exact_main_green_sha() -> None:
    workflow = _workflow()
    for token in (
        'workflows: ["CI"]',
        "github.event.workflow_run.conclusion == 'success'",
        'required=("CI" "Admin Console" "Batch Generation")',
        "head_sha=${DEPLOY_SHA}",
        "/git/ref/heads/main",
        "superseded=true",
        'git reset --hard "${DEPLOY_SHA}"',
        'test "$(git rev-parse HEAD)" = "${DEPLOY_SHA}"',
    ):
        assert token in workflow


def test_production_deploy_pins_ssh_and_does_not_discover_host_key_at_runtime() -> None:
    workflow = _workflow()
    for secret in (
        "DEPLOY_HOST",
        "DEPLOY_USER",
        "DEPLOY_PATH",
        "DEPLOY_SSH_KEY",
        "DEPLOY_KNOWN_HOSTS",
    ):
        assert f"secrets.{secret}" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "IdentitiesOnly=yes" in workflow
    assert "ssh-keyscan" not in workflow


def test_production_deploy_has_backup_migration_workers_and_smoke_gates() -> None:
    workflow = _workflow()
    for token in (
        "pg_dump -U ksu -d ksu -Fc",
        "docker compose run --rm app alembic upgrade head",
        "generation-worker",
        "media-worker",
        "payment-worker",
        "creator-partnership-worker",
        "/health/live",
        "/health/ready",
        "/health/operational",
        "/mini-app/",
        "docker compose logs --tail=200",
    ):
        assert token in workflow


def test_deploy_bootstrap_without_secrets_is_safe_and_documented() -> None:
    workflow = _workflow()
    documentation = DOC.read_text(encoding="utf-8")
    assert "configured=false" in workflow
    assert "Production deploy is not activated yet" in workflow
    assert "Required GitHub Actions secrets" in documentation
    assert "DEPLOY_KNOWN_HOSTS" in documentation
    assert "automatic database downgrade" in documentation
