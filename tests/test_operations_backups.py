from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_backup_script_is_valid_private_shell_and_verifies_archive() -> None:
    script = ROOT / "scripts" / "backup_postgres.sh"
    result = subprocess.run(
        ["sh", "-n", str(script)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    source = script.read_text(encoding="utf-8")
    for token in (
        "umask 077",
        "pg_dump",
        "--format=custom",
        "pg_restore --list",
        "sha256sum",
        "DB_BACKUP_INTERVAL_SECONDS:-10800",
        "DB_BACKUP_RETENTION_COUNT:-16",
        "DB_BACKUP_ON_START:-true",
        "postgresql+asyncpg://",
        "mktemp",
        "latest.dump",
    ):
        assert token in source, token
    assert "bot_token" not in source.lower()
    assert "telegram" not in source.lower()


def test_compose_runs_isolated_backup_worker_with_dedicated_volume() -> None:
    compose = _read("docker-compose.yml")
    assert "backup-worker:" in compose
    assert "image: postgres:17-alpine" in compose
    assert "./scripts/backup_postgres.sh:/opt/ksu/backup_postgres.sh:ro" in compose
    assert "db_backups:/backups" in compose
    assert "db_backups:" in compose
    backup_block = compose.split("  backup-worker:\n", 1)[1].split("\nvolumes:", 1)[0]
    assert "postgres:" in backup_block
    assert "condition: service_healthy" in backup_block
    assert "restart: unless-stopped" in backup_block

    # Product availability is not coupled to completion of a potentially long dump.
    app_block = compose.split("  app:\n", 1)[1].split("\n  generation-worker:", 1)[0]
    assert "backup-worker:" not in app_block


def test_production_deploy_validates_predeploy_dump_and_starts_worker() -> None:
    workflow = _read(".github/workflows/deploy-production.yml")
    assert "build_services=(" in workflow
    assert "runtime_services=(" in workflow
    assert "backup-worker" in workflow
    assert 'docker compose build "${build_services[@]}"' in workflow
    assert 'docker compose up -d --remove-orphans "${runtime_services[@]}"' in workflow
    assert 'pg_restore --list < "${backup}"' in workflow
    assert 'sha256sum "${backup}" > "${backup}.sha256"' in workflow
    assert "backup_worker_running" in workflow


def test_example_env_keeps_secrets_blank_and_documents_backup_policy() -> None:
    env_example = _read(".env.example")
    assert re.search(r"^CARD_API_KEY=$", env_example, flags=re.MULTILINE)
    assert "DB_BACKUP_INTERVAL_SECONDS=10800" in env_example
    assert "DB_BACKUP_RETENTION_COUNT=16" in env_example
    assert "DB_BACKUP_ON_START=true" in env_example
    assert "off-host" in env_example.lower()


def test_backup_runbook_requires_off_host_copy_and_restore_drill() -> None:
    document = _read("docs/DATABASE_BACKUPS.md")
    assert "Off-host durability" in document
    assert "pg_restore --list" in document
    assert "restore drill" in document.lower()
    assert "Do not send database dumps through Telegram" in document
    assert "does not automatically" in document
