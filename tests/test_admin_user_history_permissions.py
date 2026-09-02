from pathlib import Path
import uuid

from app.db.models import AdminAccount
from app.services.admin_security import has_permission

ROOT = Path(__file__).resolve().parents[1]


def test_finance_role_cannot_read_generation_or_support_content() -> None:
    finance = AdminAccount(
        user_id=uuid.uuid4(),
        role="finance",
        permission_overrides={},
        is_active=True,
    )
    assert has_permission(finance, "users.read")
    assert has_permission(finance, "users.wallet.adjust")
    assert has_permission(finance, "payments.read")
    assert not has_permission(finance, "generations.read")
    assert not has_permission(finance, "support.read")


def test_user_history_checks_each_sensitive_domain_permission() -> None:
    source = (ROOT / "app/api/v1/admin_users.py").read_text(encoding="utf-8")
    history = source.split('@router.get("/{user_id}/history")', 1)[1]

    for permission in (
        "users.wallet.adjust",
        "generations.read",
        "payments.read",
        "support.read",
        "users.notes",
    ):
        assert f'if has_permission(context.account, "{permission}"):' in history

    generation_gate = history.index('if has_permission(context.account, "generations.read"):')
    prompt_access = history.index('"prompt": item.prompt[:500]')
    support_gate = history.index('if has_permission(context.account, "support.read"):')
    support_topic = history.index('"topic": item.topic')
    payment_gate = history.index('if has_permission(context.account, "payments.read"):')
    payment_amount = history.index('"amount": str(item.amount)')

    assert generation_gate < prompt_access
    assert support_gate < support_topic
    assert payment_gate < payment_amount
