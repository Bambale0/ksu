import random
import uuid
from decimal import Decimal

import pytest

from app.core.config import DEFAULT_GENERATION_PRICING_JSON, settings
from app.db.models import AdminAccount, User
from app.db.reference_models import UserReference
from app.db.session import SessionFactory
from app.services.admin_policy import AdminPolicyError
from app.services.admin_pricing import AdminPricingService, TariffValidationError
from app.services.payments import PaymentService
from app.services.generations import GenerationService
from app.services.kie_image_contracts import KieImageContractError, normalize_kie_image_input
from app.services.model_catalog import ModelCatalog


REQUESTED_BASE_PRICES = {
    "nano-banana-pro": ("flat", Decimal("25")),
    "wan-2.7-image-pro": ("flat", Decimal("20")),
    "gpt-image-2-t2i": ("flat", Decimal("20")),
    "gpt-image-2-i2i": ("flat", Decimal("20")),
    "nano-banana-2": ("flat", Decimal("25")),
    "nano-banana-2-lite": ("flat", Decimal("25")),
    "seedream-4.5-edit": ("flat", Decimal("20")),
    "seedream-5-pro-t2i": ("flat", Decimal("20")),
    "seedream-5-pro-i2i": ("flat", Decimal("20")),
    "seedance-2.0": ("per_second", Decimal("50")),
    "seedance-2.5": ("per_second", Decimal("60")),
    "kling-2.5-turbo-pro-t2v": ("per_second", Decimal("8")),
    "kling-2.5-turbo-pro-i2v": ("per_second", Decimal("8")),
    "kling-avatar-standard": ("per_second", Decimal("100")),
    "kling-avatar-pro": ("per_second", Decimal("150")),
    "kling-3.0": ("per_second", Decimal("30")),
    "veo-3.1": ("per_second", Decimal("35")),
    "grok-video-i2v": ("per_second", Decimal("15")),
    "grok-video-1.5": ("per_second", Decimal("30")),
    "gemini-omni-video": ("per_second", Decimal("30")),
}


@pytest.mark.asyncio
async def test_admin_tariff_owns_explicit_payment_packages_without_runtime_coefficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A stale process-wide ROX/RUB rate must never change an explicit package price.
    monkeypatch.setattr(settings, "internal_credit_rub", Decimal("1.08696"))
    monkeypatch.setattr(
        settings,
        "rox_packages_json",
        '{"legacy":{"credits":"1000","amount":"1086.96","bonus_credits":"100"}}',
    )

    async with SessionFactory() as session:
        admin_user = User(
            telegram_id=random.randint(8_810_000_000_000, 8_819_999_999_999),
            first_name="Package pricing admin",
        )
        session.add(admin_user)
        await session.flush()
        admin = AdminAccount(
            user_id=admin_user.id,
            role="admin",
            permission_overrides={},
            is_active=True,
            mfa_enabled=True,
        )
        session.add(admin)
        await session.flush()

        payload = {
            "packages": {
                "p100": {"amount": "100", "currency": "RUB", "credits": "100", "bonus_credits": "0"},
                "p300": {"amount": "300", "currency": "RUB", "credits": "300", "bonus_credits": "30"},
                "p500": {"amount": "500", "currency": "RUB", "credits": "500", "bonus_credits": "50"},
                "p1000": {"amount": "1000", "currency": "RUB", "credits": "1000", "bonus_credits": "150"},
                "p2000": {"amount": "2000", "currency": "RUB", "credits": "2000", "bonus_credits": "200"},
                "p5000": {"amount": "5000", "currency": "RUB", "credits": "5000", "bonus_credits": "250"},
            }
        }
        _result, replayed = await AdminPricingService.publish(
            session,
            admin=admin,
            payload=payload,
            idempotency_key=f"test-package-pricing:{uuid.uuid4()}",
            request_id="package-pricing-live-override",
            confirmed=True,
            step_up_valid=True,
        )
        assert replayed is False

        packages = PaymentService.packages()
        assert [(p.credits, p.amount, p.bonus_credits) for p in packages.values()] == [
            (Decimal("100"), Decimal("100"), Decimal("0")),
            (Decimal("300"), Decimal("300"), Decimal("30")),
            (Decimal("500"), Decimal("500"), Decimal("50")),
            (Decimal("1000"), Decimal("1000"), Decimal("150")),
            (Decimal("2000"), Decimal("2000"), Decimal("200")),
            (Decimal("5000"), Decimal("5000"), Decimal("250")),
        ]

        # Simulate a fresh process with poisoned legacy env, then hydrate DB tariff.
        settings.rox_packages_json = (
            '{"legacy":{"credits":"5000","amount":"5434.8","bonus_credits":"200"}}'
        )
        await AdminPricingService.hydrate_runtime(session)
        hydrated = PaymentService.packages()
        assert hydrated["p5000"].amount == Decimal("5000")
        assert hydrated["p5000"].bonus_credits == Decimal("250")

        await session.rollback()


def test_payment_packages_reject_implicit_amount_and_bonus_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "internal_credit_rub", Decimal("1.08696"))
    monkeypatch.setattr(
        settings,
        "rox_packages_json",
        '{"p1000":{"credits":"1000","currency":"RUB","bonus_credits":"150"}}',
    )
    with pytest.raises(ValueError, match="explicit amount"):
        PaymentService.packages()

    monkeypatch.setattr(
        settings,
        "rox_packages_json",
        '{"p1000":{"credits":"1000","amount":"1000","currency":"RUB"}}',
    )
    with pytest.raises(ValueError, match="explicit bonus_credits"):
        PaymentService.packages()


def test_tariff_rejects_incomplete_payment_package_schema() -> None:
    from app.services.admin_pricing import validate_tariff_payload

    with pytest.raises(TariffValidationError, match="amount"):
        validate_tariff_payload(
            {"packages": {"p1000": {"credits": "1000", "bonus_credits": "150"}}}
        )


def test_requested_generation_prices_are_operator_owned_public_rox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "generation_pricing_json", DEFAULT_GENERATION_PRICING_JSON)
    overrides = ModelCatalog._pricing_overrides()

    for model_id, (price_key, expected) in REQUESTED_BASE_PRICES.items():
        assert ModelCatalog.get(model_id)
        assert Decimal(str(overrides[model_id][price_key])) == expected
        assert GenerationService._effective_unit_price(model_id=model_id, parameters={}) == expected


def test_kling_motion_prices_follow_selected_quality(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "generation_pricing_json", DEFAULT_GENERATION_PRICING_JSON)

    assert GenerationService._effective_unit_price(
        model_id="kling-motion-2.6", parameters={"mode": "720p"}
    ) == Decimal("20")
    assert GenerationService._effective_unit_price(
        model_id="kling-motion-2.6", parameters={"mode": "1080p"}
    ) == Decimal("30")
    assert GenerationService._effective_unit_price(
        model_id="kling-motion-3.0", parameters={"mode": "720p"}
    ) == Decimal("60")
    assert GenerationService._effective_unit_price(
        model_id="kling-motion-3.0", parameters={"mode": "1080p"}
    ) == Decimal("80")


def test_seedance_prices_follow_selected_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "generation_pricing_json", DEFAULT_GENERATION_PRICING_JSON)

    assert GenerationService._effective_unit_price(
        model_id="seedance-2.0", parameters={"resolution": "480p"}
    ) == Decimal("40")
    assert GenerationService._effective_unit_price(
        model_id="seedance-2.0", parameters={"resolution": "720p"}
    ) == Decimal("50")
    assert GenerationService._effective_unit_price(
        model_id="seedance-2.0", parameters={"resolution": "1080p"}
    ) == Decimal("60")
    assert GenerationService._effective_unit_price(
        model_id="seedance-2.5", parameters={"resolution": "480p"}
    ) == Decimal("50")
    assert GenerationService._effective_unit_price(
        model_id="seedance-2.5", parameters={"resolution": "720p"}
    ) == Decimal("60")
    assert GenerationService._effective_unit_price(
        model_id="seedance-2.5", parameters={"resolution": "1080p"}
    ) == Decimal("70")


def test_wan_27_pro_is_a_real_photo_generation_and_edit_model() -> None:
    spec = ModelCatalog.get("wan-2.7-image-pro")
    assert spec.media_type == "image"
    assert spec.operation == "generate_or_edit"
    assert spec.kie_model == "wan/2-7-image-pro"
    assert {"prompt", "input_urls", "n", "resolution", "thinking_mode"}.issubset(
        set(spec.known_fields)
    )

    text_payload = normalize_kie_image_input(
        spec.kie_model,
        {
            "prompt": "Editorial product shot",
            "n": 2,
            "resolution": "2K",
            "thinking_mode": True,
            "watermark": False,
        },
    )
    assert text_payload["n"] == 2
    assert text_payload["resolution"] == "2K"
    assert text_payload["thinking_mode"] is True

    edit_payload = normalize_kie_image_input(
        spec.kie_model,
        {
            "prompt": "Keep composition and replace the product color",
            "input_urls": ["https://example.test/reference.png"],
            "n": 1,
            "resolution": "2K",
            "thinking_mode": False,
        },
    )
    assert edit_payload["input_urls"]
    assert edit_payload["thinking_mode"] is False

    with pytest.raises(KieImageContractError, match="thinking_mode"):
        normalize_kie_image_input(
            spec.kie_model,
            {
                "prompt": "Keep composition and replace the product color",
                "input_urls": ["https://example.test/reference.png"],
                "n": 1,
                "resolution": "2K",
                "thinking_mode": True,
            },
        )


@pytest.mark.asyncio
async def test_admin_published_tariff_changes_real_quote_prices_and_survives_hydration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "generation_pricing_json", DEFAULT_GENERATION_PRICING_JSON)

    async with SessionFactory() as session:
        admin_user = User(
            telegram_id=random.randint(8_800_000_000_000, 8_899_999_999_999),
            first_name="Pricing admin",
        )
        session.add(admin_user)
        await session.flush()
        admin = AdminAccount(
            user_id=admin_user.id,
            role="admin",
            permission_overrides={},
            is_active=True,
            mfa_enabled=True,
        )
        session.add(admin)
        await session.flush()

        payload = {
            "generation_pricing": {
                "wan-2.7-image-pro": {"flat": 27},
                "kling-motion-3.0": {
                    "per_second": 65,
                    "by_mode": {"720p": 65, "1080p": 85},
                },
            }
        }
        _result, replayed = await AdminPricingService.publish(
            session,
            admin=admin,
            payload=payload,
            idempotency_key=f"test-pricing:{uuid.uuid4()}",
            request_id="pricing-live-override",
            confirmed=True,
            step_up_valid=True,
        )
        assert replayed is False

        spec, _clean, cost, seconds, unit_price = await GenerationService.prepare_request(
            session,
            model_id="wan-2.7-image-pro",
            prompt="Studio portrait",
            parameters={"n": 1, "resolution": "2K"},
        )
        assert spec.id == "wan-2.7-image-pro"
        assert seconds is None
        assert unit_price == Decimal("27")
        assert cost == Decimal("27.00")

        motion_url = f"https://example.test/{uuid.uuid4()}/motion.mp4"
        session.add(
            UserReference(
                user_id=admin_user.id,
                kind="video",
                status="ready",
                source_url=motion_url,
                source="mini_app_upload",
                size_bytes=1024,
                duration_ms=5000,
                probe_status="ready",
            )
        )
        await session.flush()

        spec, _clean, cost, seconds, unit_price = await GenerationService.prepare_request(
            session,
            model_id="kling-motion-3.0",
            prompt="Follow the reference motion",
            parameters={
                "input_urls": ["https://example.test/character.png"],
                "video_urls": [motion_url],
                "mode": "1080p",
                "character_orientation": "image",
            },
            # Deliberately wrong client value: pricing must use trusted media.
            billing_seconds=1,
        )
        assert spec.id == "kling-motion-3.0"
        assert seconds == 5
        # Admin publishes the base model tariff. The runtime applies the product-wide
        # video-reference multiplier after the selected quality tier is resolved.
        assert unit_price == Decimal("170")
        assert cost == Decimal("850.00")

        # Simulate a fresh process that starts with code defaults, then hydrates
        # the currently published tariff from PostgreSQL.
        settings.generation_pricing_json = DEFAULT_GENERATION_PRICING_JSON
        hydrated = await AdminPricingService.hydrate_runtime(session)
        assert Decimal(str(hydrated["wan-2.7-image-pro"]["flat"])) == Decimal("27")
        assert Decimal(str(hydrated["kling-motion-3.0"]["by_mode"]["1080p"])) == Decimal("85")

        with pytest.raises(AdminPolicyError, match="step-up"):
            await AdminPricingService.publish(
                session,
                admin=admin,
                payload={"generation_pricing": {"wan-2.7-image-pro": {"flat": 28}}},
                idempotency_key=f"test-pricing-no-step-up:{uuid.uuid4()}",
                request_id="pricing-missing-step-up",
                confirmed=True,
                step_up_valid=False,
            )

        await session.rollback()
