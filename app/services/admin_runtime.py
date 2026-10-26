from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.db.admin_models import AdminRuntimeSetting, TariffVersion
from app.db.models import AdminAccount, User
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy
from app.services.generation_provider_routing import (
    ROUTES_SETTING_KEY, configured_routes, route_options, validate_routes, validate_user_routes,
)
from app.services.neironych_balance_alerts import (
    BALANCE_ALERT_SETTING_KEY,
    NeironychBalanceAlertService,
    balance_alert_policy,
)


class AdminRuntimeService:
    SUBSCRIPTION_REQUIRED_KEY = "subscription_required"
    LAST_RELOAD_KEY = "last_config_reload"

    @staticmethod
    async def get_settings(
        session: AsyncSession,
        *,
        admin: AdminAccount,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "runtime.manage")
        rows = list((await session.scalars(select(AdminRuntimeSetting))).all())
        config = await configured_routes(session)
        balance_alert = await NeironychBalanceAlertService.policy(session)
        return {
            **{item.key: item.value for item in rows},
            BALANCE_ALERT_SETTING_KEY: balance_alert.payload(),
            ROUTES_SETTING_KEY: {**config, "options": route_options()},
        }

    @staticmethod
    async def set_neironych_balance_alert(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        enabled: bool,
        threshold_rub: object,
        expected_revision: int,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        step_up_valid: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(
            admin,
            "runtime.neironych_balance_alert",
            confirmed=confirmed,
            step_up_valid=step_up_valid,
        )
        requested = balance_alert_policy(
            enabled=enabled,
            threshold_rub=threshold_rub,
            revision=expected_revision,
        )
        request_payload = {
            "enabled": requested.enabled,
            "threshold_rub": f"{requested.threshold_rub:.2f}",
            "expected_revision": expected_revision,
        }

        async def operation() -> dict[str, Any]:
            await NeironychBalanceAlertService.acquire_lock(session)
            initial = await NeironychBalanceAlertService.policy(session)
            await session.execute(insert(AdminRuntimeSetting).values(
                key=BALANCE_ALERT_SETTING_KEY,
                value=initial.payload(),
                updated_by_admin_id=admin.id,
            ).on_conflict_do_nothing(index_elements=[AdminRuntimeSetting.key]))
            row = await session.scalar(
                select(AdminRuntimeSetting)
                .where(AdminRuntimeSetting.key == BALANCE_ALERT_SETTING_KEY)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if row is None:
                raise RuntimeError("Neironych balance alert policy could not be initialized")
            current = await NeironychBalanceAlertService.policy(session)
            if current.revision != expected_revision:
                raise ValueError("Neironych balance alert changed; reload settings before saving")
            updated = balance_alert_policy(
                enabled=requested.enabled,
                threshold_rub=requested.threshold_rub,
                revision=expected_revision + 1,
            )
            row.value = updated.payload()
            row.updated_by_admin_id = admin.id
            await session.flush()
            return updated.payload()

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="runtime.neironych_balance_alert",
            target_id=BALANCE_ALERT_SETTING_KEY,
            request_payload=request_payload,
            operation=operation,
        )

    @staticmethod
    async def set_provider_routes(
        session: AsyncSession, *, admin: AdminAccount, routes: dict[str, list[str]],
        expected_revision: int, idempotency_key: str, request_id: str, confirmed: bool,
        user_routes: dict[str, dict[str, list[str]]] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "runtime.reload", confirmed=confirmed)
        validated = validate_routes(routes)
        scoped = validate_user_routes(user_routes) if user_routes is not None else None

        async def operation() -> dict[str, Any]:
            initial = await configured_routes(session)
            await session.execute(insert(AdminRuntimeSetting).values(
                key=ROUTES_SETTING_KEY, value=initial, updated_by_admin_id=admin.id,
            ).on_conflict_do_nothing(index_elements=[AdminRuntimeSetting.key]))
            row = await session.scalar(select(AdminRuntimeSetting).where(
                AdminRuntimeSetting.key == ROUTES_SETTING_KEY,
            ).with_for_update().execution_options(populate_existing=True))
            if row is None or int(row.value["revision"]) != expected_revision:
                raise ValueError("Provider routes changed; reload settings before saving")
            if scoped:
                user_ids = [uuid.UUID(key) for key in scoped]
                existing = set(await session.scalars(select(User.id).where(User.id.in_(user_ids))))
                if existing != set(user_ids):
                    raise ValueError("User provider route scope references an unknown user")
            effective_scopes = (
                scoped if scoped is not None
                else validate_user_routes(row.value.get("user_routes", {}))
            )
            row.value = {"revision": expected_revision + 1, "routes": validated,
                         "user_routes": effective_scopes}
            row.updated_by_admin_id = admin.id
            await session.flush()
            return dict(row.value)

        return await AdminCommandLedger.execute(
            session, idempotency_key=idempotency_key, admin_user_id=admin.id,
            request_id=request_id, action="runtime.reload", target_id=ROUTES_SETTING_KEY,
            request_payload={"routes": validated, "expected_revision": expected_revision,
                             **({"user_routes": scoped} if scoped is not None else {})},
            operation=operation,
        )

    @staticmethod
    async def subscription_required(session: AsyncSession) -> bool:
        item = await session.get(AdminRuntimeSetting, AdminRuntimeService.SUBSCRIPTION_REQUIRED_KEY)
        return bool((item.value or {}).get("enabled")) if item else False

    @staticmethod
    async def set_subscription_required(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        enabled: bool,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "runtime.reload", confirmed=confirmed)
        payload = {"enabled": enabled}

        async def operation() -> dict[str, Any]:
            item = await session.get(
                AdminRuntimeSetting,
                AdminRuntimeService.SUBSCRIPTION_REQUIRED_KEY,
            )
            if item is None:
                item = AdminRuntimeSetting(
                    key=AdminRuntimeService.SUBSCRIPTION_REQUIRED_KEY,
                    value=payload,
                    updated_by_admin_id=admin.id,
                )
                session.add(item)
            else:
                item.value = payload
                item.updated_by_admin_id = admin.id
            await session.flush()
            return {"key": item.key, "enabled": enabled}

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="runtime.reload",
            target_id=AdminRuntimeService.SUBSCRIPTION_REQUIRED_KEY,
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def reload_runtime_config(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "runtime.reload", confirmed=confirmed)

        async def operation() -> dict[str, Any]:
            tariff = await session.scalar(
                select(TariffVersion)
                .where(TariffVersion.status == "published")
                .order_by(TariffVersion.version.desc())
                .limit(1)
            )
            pricing = {}
            if tariff is not None:
                payload = tariff.payload or {}
                raw = payload.get("generation_pricing")
                if isinstance(raw, dict):
                    pricing.update(raw)
                for section in ("image_prices", "video_prices"):
                    values = payload.get(section)
                    if isinstance(values, dict):
                        pricing.update(values)
                settings.generation_pricing_json = json.dumps(
                    pricing,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            now = datetime.now(UTC)
            marker = await session.get(AdminRuntimeSetting, AdminRuntimeService.LAST_RELOAD_KEY)
            marker_value = {
                "at": now.isoformat(),
                "tariff_version": tariff.version if tariff else None,
                "models_with_overrides": len(pricing),
            }
            if marker is None:
                marker = AdminRuntimeSetting(
                    key=AdminRuntimeService.LAST_RELOAD_KEY,
                    value=marker_value,
                    updated_by_admin_id=admin.id,
                )
                session.add(marker)
            else:
                marker.value = marker_value
                marker.updated_by_admin_id = admin.id
            await session.flush()
            return marker_value

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="runtime.reload",
            target_id=AdminRuntimeService.LAST_RELOAD_KEY,
            request_payload={},
            operation=operation,
        )
