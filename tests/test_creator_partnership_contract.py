from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_creator_partnership_migration_is_after_roxy_denomination() -> None:
    migration = _read("alembic/versions/0024_creator_partnership.py")
    assert 'revision = "0024_creator_partnership"' in migration
    assert 'down_revision = "0023_roxy_one_ruble_denomination"' in migration
    for table in (
        "creator_partnership_applications",
        "creator_partnership_agreements",
        "creator_partnership_grants",
    ):
        assert table in migration
    assert "uq_creator_partnership_grant_period" in migration
    assert "monthly_rox > 0" in migration


def test_public_and_admin_creator_partnership_routes_are_registered() -> None:
    router = _read("app/api/router.py")
    public = _read("app/api/v1/creator_partnership.py")
    admin = _read("app/api/v1/admin_creator_partnership.py")
    assert "creator_partnership," in router
    assert "admin_creator_partnership," in router
    assert "api_router.include_router(creator_partnership.router)" in router
    assert "api_router.include_router(admin_creator_partnership.router)" in router
    assert 'APIRouter(prefix="/creator-partnership"' in public
    assert '@router.post("/applications"' in public
    assert 'APIRouter(prefix="/admin/creator-partnership"' in admin
    assert '@router.get("/applications")' in admin
    assert '@router.get("/agreements")' in admin
    assert '"/applications/{application_id}/decision"' in admin
    assert '"/agreements/{agreement_id}/grants"' in admin


def test_sensitive_creator_admin_actions_require_confirmation_and_step_up() -> None:
    policy = _read("app/services/admin_policy.py")
    admin_api = _read("app/api/v1/admin_creator_partnership.py")
    assert '"creator_partnership.decide"' in policy
    assert '"creator_partnership.update"' in policy
    assert '"creator_partnership.grant"' in policy
    grant = policy.split('"creator_partnership.grant"', 1)[1].split("),", 1)[0]
    assert "confirmation_required=True" in grant
    assert "step_up_required=True" in grant
    assert 'Header(default=None, alias="X-Confirm-Action")' in admin_api
    assert "AdminAuthService.step_up_valid(context.session)" in admin_api
    assert 'Header(alias="Idempotency-Key"' in admin_api


def test_creator_grants_use_spend_wallet_not_withdrawable_referral_accounting() -> None:
    service = _read("app/services/creator_partnership.py")
    assert 'kind="creator_monthly_grant"' in service
    assert 'reference_type="creator_partnership"' in service
    assert 'idempotency_key=f"creator-grant:{agreement.id}:{period}"' in service
    assert "WalletService.credit(" in service
    assert "ReferralReward" not in service
    assert "PartnerService" not in service
    assert "PartnerWithdrawal" not in service


def test_creator_worker_is_deployed_and_periodic() -> None:
    compose = _read("docker-compose.yml")
    worker = _read("app/workers/creator_partnership.py")
    config = _read("app/core/config.py")
    env = _read(".env.example")
    assert "creator-partnership-worker:" in compose
    assert "python -m app.workers.creator_partnership" in compose
    assert "CreatorPartnershipService.grant_due_current_period" in worker
    assert "creator_partnership_grant_interval_seconds" in worker
    assert "creator_partnership_grant_interval_seconds: int = 3600" in config
    assert "CREATOR_PARTNERSHIP_GRANT_INTERVAL_SECONDS=3600" in env


def test_profile_uses_real_creator_partnership_application_lifecycle() -> None:
    ui = _read("app/web/mini_app/roxy-profile-cabinet.js")
    assert 'api("/api/v1/creator-partnership")' in ui
    assert 'api("/api/v1/creator-partnership/applications"' in ui
    assert 'headers: { "Idempotency-Key": crypto.randomUUID() }' in ui
    assert "channel_name" in ui
    assert "audience_size" in ui
    assert "average_views" in ui
    assert "cooperation_format" in ui
    assert "Ежемесячно" in ui
    assert "total_granted_rox" in ui
    assert "не реферальные 30% / 5%" in ui
    assert "supportComposeForm" not in ui


def test_creator_admin_console_is_real_privileged_surface() -> None:
    html = _read("app/web/admin_app/creator-partnership.html")
    js = _read("app/web/admin_app/creator-partnership.js")
    assert "Creator Partnerships" in html
    assert "/api/v1/admin/auth/login" in js
    assert "/api/v1/admin/creator-partnership/applications" in js
    assert "/api/v1/admin/creator-partnership/agreements" in js
    assert '"X-Confirm-Action": "confirmed"' in js
    assert "/api/v1/admin/auth/step-up" in js
    assert "localStorage" not in js
    assert "sessionStorage" not in js
    assert "innerHTML" not in js
    assert "eval(" not in js
