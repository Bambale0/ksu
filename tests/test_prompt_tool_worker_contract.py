from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_prompt_tool_worker_shares_uploaded_reference_storage() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    block = compose.split("  prompt-tool-worker:\n", 1)[1].split(
        "\n  creator-partnership-worker:", 1
    )[0]

    assert "python -m app.workers.prompt_tools" in block
    assert "./static/uploads:/app/static/uploads" in block


def test_operational_health_requires_prompt_tool_worker() -> None:
    health = (ROOT / "app" / "api" / "health.py").read_text(encoding="utf-8")

    for token in (
        "OPERATIONAL_WORKERS = (",
        '"prompt-tool-worker",',
        "for worker in OPERATIONAL_WORKERS",
        "await worker_health(request.app.state.redis, worker)",
    ):
        assert token in health


def test_prompt_tools_docs_cover_shared_storage_runtime_contract() -> None:
    doc = (ROOT / "docs" / "PROMPT_TOOLS.md").read_text(encoding="utf-8")

    for token in (
        "prompt-tool-worker",
        "./static/uploads:/app/static/uploads",
        "/uploads/refs/...",
        "stored reference is missing",
    ):
        assert token in doc
