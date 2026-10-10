import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-production.yml"
DOC = ROOT / "docs" / "GITHUB_PRODUCTION_DEPLOY.md"
COMPOSE = ROOT / "docker-compose.yml"
RELEASE_GATE = ROOT / ".github" / "workflows" / "roxy-release-gate.yml"
DNS_HELPER = ROOT / "finish_after_dns.sh"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_production_deploy_waits_for_exact_main_green_sha() -> None:
    workflow = _workflow()
    for token in (
        'workflows: ["CI"]',
        "github.event.workflow_run.conclusion == 'success'",
        '"CI"',
        '"Admin Console"',
        '"Batch Generation"',
        '"Mini App Playwright E2E"',
        '"ROXY E2E"',
        '"ROXY Release Gate"',
        "head_sha=${DEPLOY_SHA}",
        "/git/ref/heads/main",
        "superseded=true",
        'git checkout --detach --no-overwrite-ignore "${DEPLOY_SHA}"',
        'test "$(git rev-parse HEAD)" = "${DEPLOY_SHA}"',
    ):
        assert token in workflow


def test_release_gate_runs_for_every_main_push_so_deploy_cannot_wait_on_missing_gate() -> None:
    workflow = RELEASE_GATE.read_text(encoding="utf-8")
    push_section, pull_request_section = workflow.split("  pull_request:", 1)
    assert "  push:\n    branches: [main]" in push_section
    assert "paths:" not in push_section
    assert "paths:" in pull_request_section


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


def test_production_deploy_has_backup_all_workers_and_smoke_gates() -> None:
    workflow = _workflow()
    for token in (
        "pg_dump -U ksu -d ksu -Fc",
        "docker compose run --rm app alembic upgrade head",
        "generation-worker",
        "media-worker",
        "prompt-tool-worker",
        "payment-worker",
        "notification-worker",
        "admin-support-worker",
        "admin-campaign-worker",
        "creator-partnership-worker",
        'for service in "${runtime_services[@]}"',
        "Required production service is not running",
        "/health/live",
        "/health/ready",
        "/health/operational",
        "/mini-app/",
        "docker compose logs --tail=200",
    ):
        assert token in workflow


def test_long_running_production_services_restart_unless_stopped() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    for service in (
        "postgres",
        "redis",
        "app",
        "generation-worker",
        "media-worker",
        "payment-worker",
        "notification-worker",
        "admin-support-worker",
        "admin-campaign-worker",
        "prompt-tool-worker",
        "creator-partnership-worker",
        "backup-worker",
    ):
        match = re.search(
            rf"(?ms)^  {re.escape(service)}:\n.*?(?=^  [A-Za-z0-9_-]+:\n|\Z)",
            compose,
        )
        assert match is not None, service
        assert "restart: unless-stopped" in match.group(0), service


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


def test_dns_helper_preserves_the_active_immutable_release_image() -> None:
    helper = DNS_HELPER.read_text(encoding="utf-8")

    assert 'docker inspect "$app_container" --format \'{{.Config.Image}}\'' in helper
    assert '^ksu-app:([0-9a-f]{40})$' in helper
    assert 'export KSU_IMAGE_TAG="${BASH_REMATCH[1]}"' in helper
    assert 'docker image inspect "ksu-app:${release_sha}"' in helper
    assert 'docker compose up -d --force-recreate app' in helper
    assert "refusing to restart app as ksu-app:local" in helper


def test_production_deploy_preserves_backups_and_release_images() -> None:
    workflow = _workflow()

    for destructive_command in (
        'rm -f "${old_backup}"',
        "find backups",
        "docker image rm",
        "docker image prune",
        "docker system prune",
        "docker rmi",
    ):
        assert destructive_command not in workflow
    assert "pg_dump -U ksu -d ksu -Fc" in workflow
    assert 'pg_restore --list < "${backup}"' in workflow
    assert 'sha256sum "${backup}" > "${backup}.sha256"' in workflow
    assert "existing backups and release images are preserved" in workflow


def test_production_deploy_does_not_run_historical_media_maintenance() -> None:
    workflow = _workflow()

    assert "run_backfill" not in workflow
    assert "scripts.backfill_" not in workflow
    assert "maintenance requires a separate explicit manual action" in workflow


def test_production_deploy_fails_closed_before_changing_checkout_or_credentials() -> None:
    workflow = _workflow()

    assert "git reset --hard" not in workflow
    assert "git clean" not in workflow
    assert "git diff --quiet" in workflow
    assert "git diff --cached --quiet" in workflow
    assert 'git checkout --detach --no-overwrite-ignore "${DEPLOY_SHA}"' in workflow
    assert "ADMIN_SECURITY_KEY must be configured with at least 32 characters" in workflow
    assert "Generated persistent ADMIN_SECURITY_KEY" not in workflow
    assert "/dev/urandom" not in workflow
    assert "chmod 600 .env" not in workflow
