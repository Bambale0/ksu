from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mini_app_static_responses_are_never_stale() -> None:
    source = (ROOT / "app" / "core" / "http_security.py").read_text(encoding="utf-8")

    assert 'path == "/mini-app" or path.startswith("/mini-app/")' in source
    assert '"Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"' in source
    assert '"Pragma"] = "no-cache"' in source
    assert '"Expires"] = "0"' in source


def test_production_deploy_fails_closed_when_ssh_secrets_are_missing() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text(encoding="utf-8")

    assert "Production deploy is not configured. Missing Actions secrets" in workflow
    assert "::warning::Production deploy is not activated yet" not in workflow
    assert 'echo "configured=false"' not in workflow


def test_production_deploy_verifies_exact_mini_app_sha() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "app/web/mini_app/release.json" in workflow
    assert 'MINI_APP_RELEASE_SHA="${DEPLOY_SHA}"' in workflow
    assert "ARG MINI_APP_RELEASE_SHA=unknown" in dockerfile
    assert "expected_release=" in workflow
    assert "actual_release=" in workflow
    assert "Mini App release mismatch" in workflow
    assert "Production is healthy and Mini App serves" in workflow
