"""Payment operator report must expose only provider readiness booleans."""

import runpy
from pathlib import Path


def test_provider_readiness_is_boolean_only(monkeypatch):
    # CI tests run with app/ imports available, not scripts/ as a package.
    # Load the operator entry point by path, without invoking __main__.
    audit = runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "audit_historical_payments.py"
        ),
        run_name="ksu_operator_audit_readiness_test",
    )
    monkeypatch.setattr(
        audit["Payment2328Service"], "provider_configured", lambda: False
    )
    monkeypatch.setattr(
        audit["CardPaymentService"], "provider_configured", lambda: True
    )
    monkeypatch.setattr(
        audit["PaymentService"],
        "provider_configured",
        lambda provider: provider == "cryptobot",
    )
    report = audit["provider_readiness_snapshot"]()
    assert report == {
        "2328": {"configured": False},
        "card": {"configured": True},
        "cryptobot": {"configured": True},
        "tbank": {"configured": False},
        "yookassa": {"configured": False},
    }
    assert all(set(x) == {"configured"} for x in report.values())
    assert all(isinstance(x["configured"], bool) for x in report.values())
    assert "token" not in repr(report).lower()
    assert "password" not in repr(report).lower()
    assert "secret" not in repr(report).lower()
