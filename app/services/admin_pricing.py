from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DEFAULT_GENERATION_PRICING_JSON, settings
from app.db.admin_models import TariffVersion
from app.db.models import AdminAccount
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy
from app.services.model_catalog import ModelCatalog, UnknownModelError

ALLOWED_TARIFF_SECTIONS = frozenset(
    {
        "packages",
        "image_prices",
        "video_prices",
        "partner_exchange",
        "prompt_costs",
        "video_prompt_costs",
        "generation_pricing",
    }
)
MUSIC_MODEL_ID = "suno-v5.5"
_BASE_MUSIC_GENERATION_PRICE_ROX = Decimal(settings.music_generation_price_rox)


class TariffValidationError(ValueError):
    pass


def _validate_prices(value: Any, *, path: str = "tariff") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_prices(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_prices(item, path=f"{path}[{index}]")
        return
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TariffValidationError(f"Invalid numeric value at {path}") from exc
    if number < 0:
        raise TariffValidationError(f"Negative tariff value at {path}")


def _positive_price(value: Any, *, path: str) -> None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise TariffValidationError(f"Invalid generation price at {path}") from exc
    if number <= 0:
        raise TariffValidationError(f"Generation price must be positive at {path}")


def _validate_generation_pricing(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise TariffValidationError("generation_pricing must be an object")

    for model_id, override in value.items():
        normalized_model_id = str(model_id)
        if normalized_model_id == MUSIC_MODEL_ID:
            price_mode = "flat"
            known_fields: set[str] = set()
        else:
            try:
                spec = ModelCatalog.get(normalized_model_id)
            except UnknownModelError as exc:
                raise TariffValidationError(f"Unknown generation model: {model_id}") from exc
            price_mode = spec.price_mode
            known_fields = set(spec.known_fields)

        path = f"generation_pricing.{model_id}"
        if not isinstance(override, dict):
            _positive_price(override, path=path)
            continue

        allowed = {"flat", "per_second", "by_mode", "by_resolution"}
        unknown = sorted(set(override) - allowed)
        if unknown:
            raise TariffValidationError(
                f"Unknown generation pricing keys at {path}: {', '.join(unknown)}"
            )

        price_key = "per_second" if price_mode == "per_second" else "flat"
        if price_key not in override:
            raise TariffValidationError(f"{path} requires base {price_key} price")
        _positive_price(override[price_key], path=f"{path}.{price_key}")
        wrong_key = "flat" if price_key == "per_second" else "per_second"
        if wrong_key in override:
            raise TariffValidationError(f"{path} uses {price_key}, not {wrong_key}")

        for tier_key, parameter_key in (("by_mode", "mode"), ("by_resolution", "resolution")):
            tiers = override.get(tier_key)
            if tiers is None:
                continue
            if parameter_key not in known_fields:
                raise TariffValidationError(
                    f"{path} cannot use {tier_key}: model has no {parameter_key} parameter"
                )
            if not isinstance(tiers, dict) or not tiers:
                raise TariffValidationError(f"{path}.{tier_key} must be a non-empty object")
            for tier, price in tiers.items():
                _positive_price(price, path=f"{path}.{tier_key}.{tier}")


def validate_tariff_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        raise TariffValidationError("Tariff payload must be a non-empty object")
    unknown = sorted(set(payload) - ALLOWED_TARIFF_SECTIONS)
    if unknown:
        raise TariffValidationError(f"Unknown tariff sections: {', '.join(unknown)}")
    _validate_prices(payload)
    _validate_generation_pricing(payload.get("generation_pricing"))
    return payload


def _default_generation_pricing() -> dict[str, Any]:
    value = json.loads(DEFAULT_GENERATION_PRICING_JSON)
    return value if isinstance(value, dict) else {}


def _music_price_from_generation_pricing(merged: dict[str, Any]) -> Decimal:
    override = merged.get(MUSIC_MODEL_ID)
    if isinstance(override, dict):
        value = override.get("flat")
    else:
        value = override
    if value is None:
        return _BASE_MUSIC_GENERATION_PRICE_ROX
    return Decimal(str(value))


def _activate_generation_pricing(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Apply a published tariff over code defaults to every live pricing surface."""

    merged = _default_generation_pricing()
    section = (payload or {}).get("generation_pricing")
    if isinstance(section, dict):
        merged.update(section)
    settings.generation_pricing_json = json.dumps(merged, separators=(",", ":"), sort_keys=True)
    # Music uses its dedicated generation service, but its retail price is owned
    # by the same published admin tariff as every image/video model.
    settings.music_generation_price_rox = _music_price_from_generation_pricing(merged)
    return merged


class AdminPricingService:
    @staticmethod
    async def list_versions(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        limit: int = 50,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "pricing.read")
        rows = list(
            (
                await session.scalars(
                    select(TariffVersion)
                    .order_by(TariffVersion.version.desc())
                    .limit(max(1, min(limit, 200)))
                )
            ).all()
        )
        return {
            "items": [
                {
                    "id": str(item.id),
                    "version": item.version,
                    "status": item.status,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "created_at": item.created_at.isoformat(),
                }
                for item in rows
            ]
        }

    @staticmethod
    async def get_version(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        version_id: uuid.UUID,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "pricing.read")
        item = await session.get(TariffVersion, version_id)
        if item is None:
            raise LookupError("Tariff version not found")
        return {
            "id": str(item.id),
            "version": item.version,
            "status": item.status,
            "payload": item.payload,
            "created_by_admin_id": str(item.created_by_admin_id),
            "published_by_admin_id": (
                str(item.published_by_admin_id) if item.published_by_admin_id else None
            ),
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }

    @staticmethod
    async def current(
        session: AsyncSession,
        *,
        admin: AdminAccount,
    ) -> dict[str, Any] | None:
        AdminPolicy.require_permission(admin, "pricing.read")
        item = await session.scalar(
            select(TariffVersion)
            .where(TariffVersion.status == "published")
            .order_by(TariffVersion.version.desc())
            .limit(1)
        )
        if item is None:
            return None
        return await AdminPricingService.get_version(
            session,
            admin=admin,
            version_id=item.id,
        )

    @staticmethod
    async def hydrate_runtime(session: AsyncSession) -> dict[str, Any]:
        """Restore the latest published generation tariff from PostgreSQL."""

        item = await session.scalar(
            select(TariffVersion)
            .where(TariffVersion.status == "published")
            .order_by(TariffVersion.version.desc())
            .limit(1)
        )
        return _activate_generation_pricing(item.payload if item is not None else None)

    @staticmethod
    async def publish(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        payload: dict[str, Any],
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        step_up_valid: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(
            admin,
            "tariffs.publish",
            confirmed=confirmed,
            step_up_valid=step_up_valid,
        )
        validated = validate_tariff_payload(payload)

        async def operation() -> dict[str, Any]:
            latest = await session.scalar(
                select(TariffVersion)
                .order_by(TariffVersion.version.desc())
                .with_for_update()
                .limit(1)
            )
            next_version = (latest.version if latest else 0) + 1
            published = list(
                (
                    await session.scalars(
                        select(TariffVersion)
                        .where(TariffVersion.status == "published")
                        .with_for_update()
                    )
                ).all()
            )
            for item in published:
                item.status = "superseded"
            item = TariffVersion(
                version=next_version,
                status="published",
                payload=validated,
                created_by_admin_id=admin.id,
                published_by_admin_id=admin.id,
                published_at=datetime.now(UTC),
            )
            session.add(item)
            await session.flush()
            return {
                "id": str(item.id),
                "version": item.version,
                "status": item.status,
                "published_at": item.published_at.isoformat(),
            }

        result, replayed = await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="tariffs.publish",
            target_id=None,
            request_payload=validated,
            operation=operation,
        )
        _activate_generation_pricing(validated)
        return result, replayed

    @staticmethod
    async def count_versions(session: AsyncSession) -> int:
        return int((await session.scalar(select(func.count()).select_from(TariffVersion))) or 0)
