from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mini_app_html_stays_fresh_and_hashed_assets_are_cacheable() -> None:
    from starlette.responses import Response
    from app.core.http_security import SecurityHeadersMiddleware

    html = SecurityHeadersMiddleware._secure_response(Response(status_code=200), "request123", "/mini-app/")
    asset = SecurityHeadersMiddleware._secure_response(
        Response(status_code=200), "request123", "/mini-app/_next/static/chunks/3zq35mmk3c_25.css"
    )
    missing = SecurityHeadersMiddleware._secure_response(
        Response(status_code=404), "request123", "/mini-app/_next/static/chunks/missing.js"
    )

    assert html.headers["Cache-Control"].startswith("no-store")
    assert asset.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert "no-store" in missing.headers["Cache-Control"]


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
