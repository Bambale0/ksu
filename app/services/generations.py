import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Generation
from app.services.abuse_protection import AbuseProtectionService, GenerationAdmissionService
from app.services.billing_access import BillingAccessService
from app.services.credits import InternalCreditService
from app.services.generation_reliability import GenerationOutboxService
from app.services.model_catalog import ModelCatalog, ModelSpec
from app.services.model_routing import resolve_model_request
from app.services.seedance25_contract import normalize_seedance25_input
from app.services.wallet import WalletService

logger = logging.getLogger(__name__)

MAX_GENERATION_QUANTITY = 4


class GenerationService:
    # Kept for compatibility with older deployments/metrics. The worker no longer
    # treats this Redis list as the durable source of work.
    QUEUE_KEY = "queue:generations"
    WAKE_KEY = "wake:generations"

    @classmethod
    async def _resolve_billing_seconds(
        cls,
        session: AsyncSession,
        *,
        model_id: str,
        parameters: dict[str, Any],
        billing_seconds: int | None,
    ) -> int | None:
        if billing_seconds is not None:
            return billing_seconds
        if model_id != "grok-video-upscale":
            return None

        task_id = str(parameters.get("task_id") or "")
        if not task_id:
            return None
        source = await session.scalar(select(Generation).where(Generation.external_id == task_id))
        if source is None:
            return None
        source_seconds = (source.parameters or {}).get("_billing_seconds")
        try:
            return int(source_seconds) if source_seconds is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _apply_input_url(spec: ModelSpec, parameters: dict[str, Any], input_url: str | None) -> None:
        if not input_url:
            return
        if any(
            parameters.get(key)
            for key in (
                "image_url",
                "image_urls",
                "image_input",
                "input_urls",
                "first_frame_url",
                "first_frame",
            )
        ):
            return
        fields = set(spec.known_fields)
        if "first_frame_url" in fields:
            parameters["first_frame_url"] = input_url
        elif "image_urls" in fields:
            parameters["image_urls"] = [input_url]
        elif "input_urls" in fields:
            parameters["input_urls"] = [input_url]
        elif "image_input" in fields:
            parameters["image_input"] = [input_url]
        elif "image_url" in fields:
            parameters["image_url"] = input_url
        elif "first_frame" in fields:
            parameters["first_frame"] = input_url

    @staticmethod
    def _effective_unit_price(
        *,
        model_id: str,
        parameters: dict[str, Any],
    ) -> Decimal:
        """Resolve public ROX price, including quality-sensitive tariff tiers.

        GENERATION_PRICING_JSON is operator-owned public ROX. Older catalog defaults
        remain legacy 10-RUB credits for models that have no explicit ROXY tariff.
        """

        overrides = ModelCatalog._pricing_overrides()
        override = overrides.get(model_id)
        if isinstance(override, dict):
            for tier_key, parameter_key in (
                ("by_mode", "mode"),
                ("by_resolution", "resolution"),
            ):
                tiers = override.get(tier_key)
                selected = str(parameters.get(parameter_key) or "")
                if isinstance(tiers, dict) and selected in tiers:
                    value = Decimal(str(tiers[selected]))
                    if value <= 0:
                        raise ValueError(f"Model tariff {model_id}.{tier_key}.{selected} must be positive")
                    return value

        value = ModelCatalog.unit_price(model_id)
        if model_id not in overrides:
            value = InternalCreditService.legacy_credits_to_rox(value)
        if value <= 0:
            raise ValueError(f"Model tariff {model_id} must be positive")
        return value

    @staticmethod
    def _provider_model_snapshot(spec: ModelSpec, clean: dict[str, Any]) -> str:
        # Veo uses a dedicated API where veo_model is the actual upstream variant.
        # Every Market-backed model uses the catalog's exact callable model id.
        if spec.id == "veo-3.1":
            return str(clean.get("veo_model") or spec.kie_model)
        return spec.kie_model

    @classmethod
    async def prepare_request(
        cls,
        session: AsyncSession,
        *,
        model_id: str,
        prompt: str,
        input_url: str | None = None,
        parameters: dict[str, Any] | None = None,
        billing_seconds: int | None = None,
    ) -> tuple[ModelSpec, dict[str, Any], Decimal, int | None, Decimal]:
        merged = dict(parameters or {})
        if prompt and not merged.get("prompt"):
            merged["prompt"] = prompt

        routed = resolve_model_request(model_id, merged, input_url=input_url)
        merged = routed.parameters

        if routed.model_id == "seedance-2.5":
            # Validate the current provider contract before wallet debit. This also
            # normalizes old saved drafts (for example obsolete fixed_lens).
            merged = normalize_seedance25_input(merged)

        resolved_seconds = await cls._resolve_billing_seconds(
            session,
            model_id=routed.model_id,
            parameters=merged,
            billing_seconds=billing_seconds,
        )
        spec, clean, _catalog_cost, seconds, _catalog_unit_price = ModelCatalog.prepare(
            routed.model_id,
            merged,
            billing_seconds=resolved_seconds,
        )
        unit_price = cls._effective_unit_price(model_id=spec.id, parameters=clean)
        multiplier = Decimal(seconds) if spec.price_mode == "per_second" and seconds is not None else Decimal("1")
        cost_rox = (unit_price * multiplier).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return spec, clean, cost_rox, seconds, unit_price

    @classmethod
    def _generation_parameters(
        cls,
        *,
        clean: dict[str, Any],
        requested_model_id: str,
        spec: ModelSpec,
        provider_model: str,
        seconds: int | None,
        unit_price: Decimal,
        retail_cost_rox: Decimal,
        admin_free: bool,
        batch_id: uuid.UUID | None = None,
        batch_index: int = 1,
        batch_size: int = 1,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            **clean,
            "_requested_model_id": requested_model_id,
            "_auto_routed": spec.id != requested_model_id,
            "_auto_mode": "reference" if any(clean.get(key) for key in ("image_urls", "input_urls", "image_input", "image_url", "first_frame_url", "reference_image_urls", "video_urls", "video_url", "first_clip_url", "reference_video_urls")) else "text",
            "_model_id": spec.id,
            "_model_title": spec.title,
            "_model_family": spec.family,
            "_operation": spec.operation,
            "_media_type": spec.media_type,
            "_kie_model": spec.kie_model,
            "_provider_model": provider_model,
            "_billing_mode": spec.price_mode,
            "_billing_seconds": seconds,
            "_unit_price_rox": str(unit_price),
            "_retail_cost_rox": str(retail_cost_rox),
            "_admin_free": admin_free,
            **(
                {"_admin_free_generation": True, "_quoted_cost_rox": str(retail_cost_rox)}
                if admin_free
                else {}
            ),
        }
        if batch_id is not None and batch_size > 1:
            params.update(
                {
                    "_batch_id": str(batch_id),
                    "_batch_index": batch_index,
                    "_batch_size": batch_size,
                }
            )
        return params

    @classmethod
    async def create_many(
        cls,
        session: AsyncSession,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        model_id: str,
        prompt: str = "",
        input_url: str | None = None,
        parameters: dict[str, Any] | None = None,
        billing_seconds: int | None = None,
        quantity: int = 1,
        source_feed_gen_id: uuid.UUID | None = None,
        parent_generation_id: uuid.UUID | None = None,
        action_type: str | None = None,
    ) -> list[Generation]:
        requested = int(quantity)
        if requested < 1 or requested > MAX_GENERATION_QUANTITY:
            raise ValueError(f"Generation quantity must be between 1 and {MAX_GENERATION_QUANTITY}")

        spec, clean, retail_cost_rox, seconds, unit_price = await cls.prepare_request(
            session,
            model_id=model_id,
            prompt=prompt,
            input_url=input_url,
            parameters=parameters,
            billing_seconds=billing_seconds,
        )
        billing = await BillingAccessService.decision(
            session,
            user_id=user_id,
            retail_cost=retail_cost_rox,
        )
        charge_rox = billing.effective_cost
        total_charge_rox = (charge_rox * Decimal(requested)).quantize(Decimal("0.01"))

        # Admins are free, not unbounded: request/provider resource safety remains
        # active. Passing zero only removes spend accounting from the admission gate.
        await AbuseProtectionService.generation_rate(redis, user_id, amount=requested)
        await GenerationAdmissionService.enforce(
            session,
            user_id=user_id,
            next_cost=total_charge_rox,
            quantity=requested,
        )

        provider_model = cls._provider_model_snapshot(spec, clean)
        batch_id = uuid.uuid4() if requested > 1 else None
        generations: list[Generation] = []
        for index in range(1, requested + 1):
            generation = Generation(
                user_id=user_id,
                kind=spec.operation,
                prompt=str(clean.get("prompt") or prompt or ""),
                input_url=input_url,
                cost_rox=charge_rox,
                provider="kie",
                parameters=cls._generation_parameters(
                    clean=clean,
                    requested_model_id=model_id,
                    spec=spec,
                    provider_model=provider_model,
                    seconds=seconds,
                    unit_price=unit_price,
                    retail_cost_rox=billing.retail_cost,
                    admin_free=billing.admin_free,
                    batch_id=batch_id,
                    batch_index=index,
                    batch_size=requested,
                ),
                status="queued",
                source_feed_gen_id=source_feed_gen_id,
                parent_generation_id=parent_generation_id,
                action_type=action_type,
                publication_scope="private",
                is_public_feed=False,
                is_profile_visible=False,
                feed_prompt_visible=False if source_feed_gen_id else False,
                feed_references_visible=False if source_feed_gen_id else False,
            )
            session.add(generation)
            generations.append(generation)

        await session.flush()

        for generation in generations:
            GenerationOutboxService.add(session, generation.id)
            if charge_rox > 0:
                await WalletService.debit(
                    session,
                    user_id=user_id,
                    amount=charge_rox,
                    kind="generation",
                    reference_type="generation",
                    reference_id=str(generation.id),
                    idempotency_key=f"generation:{generation.id}:charge",
                )
        await session.commit()

        try:
            await redis.rpush(cls.WAKE_KEY, *[str(generation.id) for generation in generations])
        except RedisError:
            logger.warning(
                "Redis wake-up failed for %s generation(s); outbox will recover them",
                len(generations),
            )
        return generations

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        model_id: str,
        prompt: str = "",
        input_url: str | None = None,
        parameters: dict[str, Any] | None = None,
        billing_seconds: int | None = None,
        source_feed_gen_id: uuid.UUID | None = None,
        parent_generation_id: uuid.UUID | None = None,
        action_type: str | None = None,
    ) -> Generation:
        generations = await cls.create_many(
            session,
            redis,
            user_id=user_id,
            model_id=model_id,
            prompt=prompt,
            input_url=input_url,
            parameters=parameters,
            billing_seconds=billing_seconds,
            quantity=1,
            source_feed_gen_id=source_feed_gen_id,
            parent_generation_id=parent_generation_id,
            action_type=action_type,
        )
        return generations[0]
