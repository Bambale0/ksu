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
        'required=("CI" "Admin Console" "Batch Generation" "Mini App Playwright E2E")',
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
        "prompt-tool-worker",
        "payment-worker",
        "creator-partnership-worker",
        "/health/live",
        "/health/ready",
        "/health/operational",
        "/mini-app/",
        "docker compose logs --tail=200",
    ):
        assert token in workflow


def test_deploy_without_secrets_fails_closed_and_is_documented() -> None:
    workflow = _workflow()
    documentation = DOC.read_text(encoding="utf-8")

    assert "configured=false" not in workflow
    assert "Production deploy is not activated yet" not in workflow
    assert "Production deploy is not configured. Missing Actions secrets" in workflow
    assert "Missing required deployment secrets fails the workflow" in documentation
    assert "Required GitHub Actions secrets" in documentation
    assert "DEPLOY_KNOWN_HOSTS" in documentation
    assert "automatic database downgrade" in documentation


def test_production_deploy_proves_the_exact_mini_app_release() -> None:
    workflow = _workflow()
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "app/web/mini_app/release.json" in workflow
    assert 'MINI_APP_RELEASE_SHA="${DEPLOY_SHA}"' in workflow
    assert "ARG MINI_APP_RELEASE_SHA=unknown" in dockerfile
    assert "MINI_APP_RELEASE_SHA" in dockerfile
    assert "expected_release=" in workflow
    assert "actual_release=" in workflow
    assert "Mini App release mismatch" in workflow
    assert "Production is healthy and Mini App serves" in workflow
