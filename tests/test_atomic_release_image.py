from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-production.yml"

APPLICATION_SERVICES = (
    "app",
    "generation-worker",
    "media-worker",
    "prompt-tool-worker",
    "payment-worker",
    "notification-worker",
    "admin-support-worker",
    "admin-campaign-worker",
    "creator-partnership-worker",
)


def test_every_python_runtime_uses_one_release_tagged_image() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    for service in APPLICATION_SERVICES:
        match = re.search(
            rf"(?ms)^  {re.escape(service)}:\n.*?(?=^  [A-Za-z0-9_-]+:\n|\Z)",
            compose,
        )
        assert match is not None, service
        block = match.group(0)
        assert 'image: "ksu-app:${KSU_IMAGE_TAG:-local}"' in block, service
        assert "build: ." in block, service


def test_production_deploy_builds_once_force_recreates_and_proves_image_identity() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for token in (
        'export KSU_IMAGE_TAG="${DEPLOY_SHA}"',
        'expected_image_name="ksu-app:${KSU_IMAGE_TAG}"',
        'docker compose build --build-arg MINI_APP_RELEASE_SHA="${DEPLOY_SHA}" app',
        'docker image inspect "${expected_image_name}" --format \'{{.Id}}\'',
        'docker compose up -d --force-recreate --remove-orphans "${runtime_services[@]}"',
        'for service in "${application_services[@]}"',
        'actual_image_id="$(docker inspect "${container_id}" --format \'{{.Image}}\')"',
        'if [[ "${actual_image_id}" != "${expected_image_id}" ]]',
        "image mismatch",
    ):
        assert token in workflow
