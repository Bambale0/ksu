from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import TariffVersion
from app.db.models import AdminAccount
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy

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


def validate_tariff_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        raise TariffValidationError("Tariff payload must be a non-empty object")
    unknown = sorted(set(payload) - ALLOWED_TARIFF_SECTIONS)
    if unknown:
        raise TariffValidationError(f"Unknown tariff sections: {', '.join(unknown)}")
    _validate_prices(payload)
    return payload


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

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="tariffs.publish",
            target_id=None,
            request_payload=validated,
            operation=operation,
        )

    @staticmethod
    async def count_versions(session: AsyncSession) -> int:
        return int((await session.scalar(select(func.count()).select_from(TariffVersion))) or 0)
