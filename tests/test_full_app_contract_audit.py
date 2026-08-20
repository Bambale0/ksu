from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.billing_access import BillingAccessService
from app.services.generation_provider import GenerationProviderService
from app.services.kling_current_contract import (
    KLING_25_I2V_PROVIDER,
    KLING_25_T2V_PROVIDER,
    KLING_AVATAR_PRO_PROVIDER,
    KLING_AVATAR_STANDARD_PROVIDER,
)
from app.services.model_catalog import ModelCatalog
from app.services.model_presentation import presentation_for


class _ScalarSession:
    def __init__(self, value: object | None) -> None:
        self.value = value

    async def scalar(self, _statement):  # type: ignore[no-untyped-def]
        return self.value


@pytest.mark.asyncio
async def test_active_admin_customer_cost_is_zero_but_retail_is_preserved() -> None:
    decision = await BillingAccessService.decision(
        _ScalarSession(uuid.uuid4()),  # type: ignore[arg-type]
        user_id=uuid.uuid4(),
        retail_cost=Decimal("125.50"),
    )
    assert decision.admin_free is True
    assert decision.retail_cost == Decimal("125.50")
    assert decision.effective_cost == Decimal("0.00")


@pytest.mark.asyncio
async def test_regular_user_keeps_retail_customer_cost() -> None:
    decision = await BillingAccessService.decision(
        _ScalarSession(None),  # type: ignore[arg-type]
        user_id=uuid.uuid4(),
        retail_cost=Decimal("125.50"),
    )
    assert decision.admin_free is False
    assert decision.effective_cost == Decimal("125.50")


def test_every_runtime_model_has_provider_and_customer_presentation() -> None:
    for model in ModelCatalog.list():
        assert str(model["id"]).strip()
        assert str(model["kie_model"]).strip(), model["id"]
        presentation = presentation_for(model)
        assert str(presentation["title"]).strip(), model["id"]
        assert str(presentation["product_key"]).strip(), model["id"]
        assert str(presentation["product_title"]).strip(), model["id"]


def test_current_kling_provider_ids_match_callable_contract() -> None:
    expected = {
        "kling-2.5-turbo-pro-t2v": KLING_25_T2V_PROVIDER,
        "kling-2.5-turbo-pro-i2v": KLING_25_I2V_PROVIDER,
        "kling-avatar-standard": KLING_AVATAR_STANDARD_PROVIDER,
        "kling-avatar-pro": KLING_AVATAR_PRO_PROVIDER,
    }
    for model_id, provider_model in expected.items():
        assert ModelCatalog.get(model_id).kie_model == provider_model


def test_kling_video_motion_avatar_are_not_one_customer_family() -> None:
    groups = {
        model_id: presentation_for(ModelCatalog.get(model_id).public_dict())["family_group"]
        for model_id in (
            "kling-2.5-turbo-pro-t2v",
            "kling-motion-3.0",
            "kling-avatar-pro",
        )
    }
    assert groups["kling-2.5-turbo-pro-t2v"] == "kling-video"
    assert groups["kling-motion-3.0"] == "kling-motion"
    assert groups["kling-avatar-pro"] == "kling-avatar"
    assert len(set(groups.values())) == 3


def test_provider_submission_prefers_generation_snapshot() -> None:
    class GenerationStub:
        parameters = {
            "_model_id": "gpt-image-2-t2i",
            "_kie_model": "historical/provider-model",
            "_provider_model": "frozen/provider-model",
        }

    assert GenerationProviderService._provider_model_snapshot(GenerationStub()) == "frozen/provider-model"  # type: ignore[arg-type]


def test_provider_payload_strips_all_internal_identity_and_billing_fields() -> None:
    class GenerationStub:
        prompt = "hello"
        input_url = None
        parameters = {
            "prompt": "hello",
            "aspect_ratio": "1:1",
            "_provider_model": "secret/provider-routing",
            "_kie_model": "secret/provider-routing",
            "_admin_free": True,
            "_retail_cost_rox": "99.00",
        }

    assert GenerationProviderService._input_for(GenerationStub()) == {  # type: ignore[arg-type]
        "prompt": "hello",
        "aspect_ratio": "1:1",
    }


def test_mini_app_loads_contract_guard_without_global_fetch_monkeypatch() -> None:
    root = Path(__file__).resolve().parents[1]
    app = (root / "frontend/mini-app/components/roxy-app.tsx").read_text(encoding="utf-8")
    api = (root / "frontend/mini-app/lib/api.ts").read_text(encoding="utf-8")
    telegram = (root / "frontend/mini-app/lib/telegram.ts").read_text(encoding="utf-8")

    assert '"Бесплатно"' in app
    assert "window.fetch =" not in app
    assert "window.fetch =" not in api
    assert 'headers["X-Telegram-Init-Data"] = initData' in telegram


def test_wallet_customer_copy_is_normalized_to_rox() -> None:
    root = Path(__file__).resolve().parents[1]
    app = (root / "frontend/mini-app/components/roxy-app.tsx").read_text(encoding="utf-8")
    assert "balance_rox" in app
    assert " ROX" in app
    assert "кр." not in app
