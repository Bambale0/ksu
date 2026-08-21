from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_current_documentation_entrypoints_exist() -> None:
    for relative in (
        "README.md",
        "docs/API_REFERENCE.md",
        "docs/OPERATIONS_RUNBOOK.md",
        "docs/GENERATION_MINI_APP.md",
        "docs/ADMIN_SECURITY.md",
        "docs/ADMIN_CONTOUR.md",
        "docs/ADMIN_WEB_REMOVAL_AUDIT_2026-08-21.md",
    ):
        path = ROOT / relative
        assert path.is_file(), relative
        assert path.stat().st_size > 500, relative


def test_readme_documents_current_runtime_surfaces() -> None:
    readme = _read("README.md")
    for token in (
        "/mini-app/",
        "Telegram-admin/API-only",
        "retired static `/admin-app/` web surface is not mounted or shipped",
        "/api/v1/uploads/kie",
        "generation-worker",
        "KIE_UPLOAD_BASE_URL",
        "ADMIN_SECURITY_KEY",
        "transactional outbox",
        "docs/API_REFERENCE.md",
        "docs/OPERATIONS_RUNBOOK.md",
        "docs/GENERATION_MINI_APP.md",
        "docs/ADMIN_SECURITY.md",
    ):
        assert token in readme, token


def test_operations_runbook_covers_every_compose_service_and_webhook() -> None:
    compose = _read("docker-compose.yml")
    runbook = _read("docs/OPERATIONS_RUNBOOK.md")
    for service in ("postgres", "redis", "app", "generation-worker"):
        assert f"  {service}:" in compose
        assert service in runbook
    for route in (
        "/webhooks/telegram",
        "/webhooks/kie",
        "/webhooks/payments/cryptobot",
        "/webhooks/payments/tbank",
        "/webhooks/payments/yookassa",
    ):
        assert route in runbook, route


def test_generation_docs_cover_schema_state_and_server_pricing() -> None:
    doc = _read("docs/GENERATION_MINI_APP.md")
    for token in (
        "ui_schema",
        "schema_version",
        "localStorage",
        "Seedance",
        "Wan 2.7",
        "Kling Motion",
        "billing_seconds",
        "server",
        "suggestions are not strict enums",
    ):
        assert token in doc, token


def test_admin_docs_mark_static_web_admin_removed() -> None:
    contour = _read("docs/ADMIN_CONTOUR.md")
    audit = _read("docs/ADMIN_WEB_REMOVAL_AUDIT_2026-08-21.md")
    security = _read("docs/ADMIN_SECURITY.md")

    assert "The retired static browser admin (`/admin-app`) is no longer mounted or shipped" in contour
    assert "Telegram-admin/API-only" in contour
    assert "app/bot/handlers/admin_web_removed.py" in contour
    assert "static `/admin-app/` web surface is not mounted or shipped" in audit
    assert "old `admin:web` callbacks" in audit
    assert "ADMIN_SECURITY_KEY" in security
    assert "step-up" in security
