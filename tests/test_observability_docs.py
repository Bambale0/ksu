from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_observability_runbook_and_alerts_exist() -> None:
    for relative in ("docs/OBSERVABILITY.md", "ops/prometheus-alerts.yml"):
        path = ROOT / relative
        assert path.is_file(), relative
        assert path.stat().st_size > 500, relative


def test_observability_runbook_documents_runtime_contract() -> None:
    doc = _read("docs/OBSERVABILITY.md")
    for token in (
        "/metrics",
        "/health/operational",
        "METRICS_BEARER_TOKEN",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "ksu.generation-worker",
        "ksu.payment-worker",
        "ksu_generation_outbox_oldest_pending_seconds",
        "observability:worker:generation-worker:heartbeat",
        "high-cardinality",
    ):
        assert token in doc, token


def test_readme_exposes_observability_entrypoints() -> None:
    readme = _read("README.md")
    for token in (
        "/metrics",
        "/health/operational",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "ops/prometheus-alerts.yml",
        "transactional outbox",
        "ADMIN_SECURITY_KEY",
        "KIE_UPLOAD_BASE_URL",
    ):
        assert token in readme, token


def test_alert_rules_cover_worker_and_paid_work_pipeline() -> None:
    rules = _read("ops/prometheus-alerts.yml")
    for token in (
        "KsuWorkerDown",
        "KsuGenerationOutboxBacklog",
        "KsuKieCircuitOpen",
        "KsuPaymentCreationUnknown",
        "KsuPaymentReconciliationFailuresIncreasing",
    ):
        assert token in rules, token
