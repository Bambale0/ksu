from __future__ import annotations

import re
from pathlib import Path

from app.core.runtime_services import APPLICATION_SERVICES, OPERATIONAL_WORKERS

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
DEPLOY = (ROOT / ".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
MINIAPP_E2E = (ROOT / ".github/workflows/miniapp-playwright.yml").read_text(encoding="utf-8")
ROXY_E2E = (ROOT / ".github/workflows/e2e.yml").read_text(encoding="utf-8")
RELEASE_GATE = (ROOT / ".github/workflows/roxy-release-gate.yml").read_text(encoding="utf-8")


def _compose_service_block(service: str) -> str:
    marker = f"  {service}:\n"
    start = COMPOSE.index(marker) + len(marker)
    match = re.search(r"^  [a-z0-9][a-z0-9-]*:\s*$", COMPOSE[start:], flags=re.MULTILINE)
    end = start + match.start() if match else len(COMPOSE)
    return COMPOSE[start:end]


def _bash_array(name: str) -> tuple[str, ...]:
    match = re.search(
        rf"{re.escape(name)}=\(\n(?P<body>.*?)\n\s*\)",
        DEPLOY,
        flags=re.DOTALL,
    )
    assert match is not None, f"{name} array missing from deploy workflow"
    return tuple(
        line.strip().strip('"')
        for line in match.group("body").splitlines()
        if line.strip() and not line.strip().startswith("#")
    )


def test_all_application_services_share_one_release_image() -> None:
    assert APPLICATION_SERVICES[0] == "app"
    assert OPERATIONAL_WORKERS == APPLICATION_SERVICES[1:]
    for service in APPLICATION_SERVICES:
        block = _compose_service_block(service)
        assert 'image: "ksu-app:${KSU_IMAGE_TAG:-local}"' in block, service


def test_deploy_recreates_every_application_service() -> None:
    assert _bash_array("application_services") == APPLICATION_SERVICES
    assert 'docker compose build --build-arg MINI_APP_RELEASE_SHA="${DEPLOY_SHA}" app' in DEPLOY
    assert 'docker compose up -d --force-recreate --remove-orphans "${runtime_services[@]}"' in DEPLOY
    assert 'actual_image_id="$(docker inspect "${container_id}" --format \'{{.Image}}\')"' in DEPLOY
    assert 'actual_image_id}" != "${expected_image_id}' in DEPLOY


def test_workers_without_native_heartbeat_use_runtime_wrapper() -> None:
    expected_wrapped = {
        "notification-worker": "app.workers.notifications",
        "admin-campaign-worker": "app.workers.admin_campaigns",
        "creator-partnership-worker": "app.workers.creator_partnership",
    }
    for service, module in expected_wrapped.items():
        block = _compose_service_block(service)
        assert "app.workers.heartbeat_runner" in block
        assert module in block


def test_production_waits_for_complete_release_workflows() -> None:
    required = {
        "CI",
        "Admin Console",
        "Batch Generation",
        "Mini App Playwright E2E",
        "ROXY E2E",
        "ROXY Release Gate",
    }
    match = re.search(r"required=\(\n(?P<body>.*?)\n\s*\)", DEPLOY, flags=re.DOTALL)
    assert match is not None
    configured = set(re.findall(r'"([^"]+)"', match.group("body")))
    assert configured == required


def test_browser_checks_have_distinct_names_and_release_gate_always_runs() -> None:
    assert "  miniapp-e2e:\n    name: miniapp-e2e" in MINIAPP_E2E
    assert "jobs:\n  e2e:" in ROXY_E2E
    assert "paths:" not in RELEASE_GATE
    assert "  release-gate:\n    name: release-gate" in RELEASE_GATE
