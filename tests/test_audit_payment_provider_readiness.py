"""Payment operator report must expose only provider readiness booleans."""

from scripts import audit_historical_payments as audit


def test_provider_readiness_is_boolean_only(monkeypatch):
    monkeypatch.setattr(
        audit.Payment2328Service, "provider_configured", lambda: False
    )
    monkeypatch.setattr(
        audit.CardPaymentService, "provider_configured", lambda: True
    )
    monkeypatch.setattr(
        audit.PaymentService,
        "provider_configured",
        lambda provider: provider == "cryptobot",
    )
    report = audit.provider_readiness_snapshot()
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
