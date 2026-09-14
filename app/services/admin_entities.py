from __future__ import annotations

import base64
import importlib
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect

from app.db.base import Base
from app.db.models import AdminAccount
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy

_MODEL_MODULES = (
    "app.db.action_context_models",
    "app.db.admin_content_models",
    "app.db.admin_models",
    "app.db.batch_models",
    "app.db.creator_partner_models",
    "app.db.feed_models",
    "app.db.history_models",
    "app.db.media_models",
    "app.db.models",
    "app.db.notification_models",
    "app.db.onboarding_models",
    "app.db.partner_wallet_models",
    "app.db.payment_models",
    "app.db.profile_models",
    "app.db.prompt_tool_models",
    "app.db.reference_models",
    "app.db.referral_models",
    "app.db.reliability_models",
    "app.db.social_models",
)
for _module in _MODEL_MODULES:
    importlib.import_module(_module)


FINANCIAL_TABLES = frozenset(
    {
        "wallets",
        "wallet_transactions",
        "payments",
        "payment_requests",
        "payment_refund_requests",
        "payment_reversals",
        "promo_codes",
        "promo_redemptions",
        "referral_rewards",
        "referral_reward_reversals",
        "partner_withdrawals",
        "partner_withdrawal_requests",
        "partner_wallet_transfers",
        "tariff_versions",
    }
)

READ_ONLY_TABLES = FINANCIAL_TABLES | frozenset(
    {
        "admin_commands",
        "admin_audit_logs",
        "admin_sessions",
        "support_outbox",
        "generation_outbox",
        "prompt_tool_outbox",
        "notification_deliveries",
        "notification_campaign_deliveries",
    }
)

_SENSITIVE_TOKENS = (
    "password",
    "secret",
    "token",
    "recovery",
    "hash",
    "cookie",
    "authorization",
    "webhook",
    "api_key",
)


def _mapper_registry() -> dict[str, type[Any]]:
    return {
        mapper.local_table.name: mapper.class_
        for mapper in Base.registry.mappers
        if mapper.local_table is not None
    }


def _is_sensitive(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in _SENSITIVE_TOKENS)


def _json_value(value: Any) -> Any:
    if isinstance(value, (uuid.UUID, datetime, Decimal)):
        return str(value) if not isinstance(value, datetime) else value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _column_kind(column: Any) -> str:
    if isinstance(column.type, Boolean):
        return "boolean"
    if isinstance(column.type, Integer):
        return "integer"
    if isinstance(column.type, Numeric):
        return "number"
    if isinstance(column.type, DateTime):
        return "datetime"
    if isinstance(column.type, (String, Text)):
        return "text"
    try:
        python_type = column.type.python_type
    except (AttributeError, NotImplementedError):
        python_type = object
    if python_type is dict:
        return "json"
    if python_type is list:
        return "json"
    if python_type is uuid.UUID:
        return "uuid"
    return "json"


def _editable_columns(table_name: str, model: type[Any]) -> list[Any]:
    if table_name in READ_ONLY_TABLES:
        return []
    mapper = sa_inspect(model)
    editable = []
    for column in mapper.columns:
        if column.primary_key or column.foreign_keys:
            continue
        if column.key in {"created_at", "updated_at"}:
            continue
        if _is_sensitive(column.key):
            continue
        if column.key.endswith("_id"):
            continue
        editable.append(column)
    return editable


def _encode_record_key(model: type[Any], row: Any) -> str:
    mapper = sa_inspect(model)
    values = [_json_value(getattr(row, column.key)) for column in mapper.primary_key]
    raw = json.dumps(values, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_record_key(model: type[Any], record_key: str) -> list[Any]:
    padding = "=" * (-len(record_key) % 4)
    try:
        values = json.loads(
            base64.urlsafe_b64decode((record_key + padding).encode("ascii")).decode("utf-8")
        )
    except Exception as exc:
        raise ValueError("Invalid entity record key") from exc
    mapper = sa_inspect(model)
    if not isinstance(values, list) or len(values) != len(mapper.primary_key):
        raise ValueError("Invalid entity record key")
    result = []
    for column, value in zip(mapper.primary_key, values, strict=True):
        try:
            python_type = column.type.python_type
        except (AttributeError, NotImplementedError):
            python_type = str
        if python_type is uuid.UUID:
            result.append(uuid.UUID(str(value)))
        elif python_type is int:
            result.append(int(value))
        elif python_type is str:
            result.append(str(value))
        else:
            result.append(value)
    return result


def _coerce(column: Any, value: Any) -> Any:
    if value is None:
        if not column.nullable:
            raise ValueError(f"{column.key} cannot be null")
        return None
    if isinstance(column.type, Boolean):
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"{column.key} must be boolean")
    if isinstance(column.type, Integer):
        return int(value)
    if isinstance(column.type, Numeric):
        return Decimal(str(value))
    if isinstance(column.type, DateTime):
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if isinstance(column.type, (String, Text)):
        return str(value)
    try:
        python_type = column.type.python_type
    except (AttributeError, NotImplementedError):
        python_type = object
    if python_type is uuid.UUID:
        return uuid.UUID(str(value))
    if python_type in {dict, list} and isinstance(value, str):
        return json.loads(value)
    return value


class AdminEntityService:
    @staticmethod
    def _models_for(admin: AdminAccount) -> dict[str, type[Any]]:
        models = _mapper_registry()
        if admin.role == "finance":
            return {name: model for name, model in models.items() if name in FINANCIAL_TABLES}
        return models

    @classmethod
    def catalog(cls, *, admin: AdminAccount) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "entities.read")
        items = []
        for table_name, model in sorted(cls._models_for(admin).items()):
            mapper = sa_inspect(model)
            editable = {column.key for column in _editable_columns(table_name, model)}
            fields = []
            for column in mapper.columns:
                fields.append(
                    {
                        "name": column.key,
                        "type": _column_kind(column),
                        "nullable": bool(column.nullable),
                        "primary_key": bool(column.primary_key),
                        "foreign_key": bool(column.foreign_keys),
                        "sensitive": _is_sensitive(column.key),
                        "editable": column.key in editable,
                    }
                )
            items.append(
                {
                    "name": table_name,
                    "label": table_name.replace("_", " ").title(),
                    "category": "finance" if table_name in FINANCIAL_TABLES else "entity",
                    "editable": bool(editable),
                    "fields": fields,
                }
            )
        return {"items": items, "total": len(items)}

    @classmethod
    def _model(cls, admin: AdminAccount, entity: str) -> type[Any]:
        model = cls._models_for(admin).get(entity)
        if model is None:
            raise LookupError("Entity not found")
        return model

    @staticmethod
    def _row_view(table_name: str, model: type[Any], row: Any) -> dict[str, Any]:
        mapper = sa_inspect(model)
        editable = {column.key for column in _editable_columns(table_name, model)}
        values: dict[str, Any] = {}
        for column in mapper.columns:
            if _is_sensitive(column.key):
                values[column.key] = "[redacted]"
            else:
                values[column.key] = _json_value(getattr(row, column.key))
        return {
            "record_key": _encode_record_key(model, row),
            "values": values,
            "editable_fields": sorted(editable),
        }

    @classmethod
    async def list_rows(
        cls,
        session: AsyncSession,
        *,
        admin: AdminAccount,
        entity: str,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "entities.read")
        model = cls._model(admin, entity)
        mapper = sa_inspect(model)
        stmt = select(model)
        count_stmt = select(func.count()).select_from(model)
        raw_query = str(q or "").strip()
        if raw_query:
            conditions = []
            for column in mapper.columns:
                if _is_sensitive(column.key):
                    continue
                if isinstance(column.type, (String, Text)) or column.primary_key:
                    conditions.append(cast(column, String).ilike(f"%{raw_query}%"))
            if conditions:
                predicate = or_(*conditions)
                stmt = stmt.where(predicate)
                count_stmt = count_stmt.where(predicate)

        if "created_at" in mapper.columns:
            stmt = stmt.order_by(mapper.columns.created_at.desc())
        else:
            stmt = stmt.order_by(*[column.desc() for column in mapper.primary_key])

        bounded_limit = max(1, min(limit, 100))
        bounded_offset = max(0, min(offset, 100_000))
        rows = list(
            (
                await session.scalars(
                    stmt.offset(bounded_offset).limit(bounded_limit)
                )
            ).all()
        )
        return {
            "entity": entity,
            "items": [cls._row_view(entity, model, row) for row in rows],
            "total": int((await session.scalar(count_stmt)) or 0),
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

    @classmethod
    async def detail(
        cls,
        session: AsyncSession,
        *,
        admin: AdminAccount,
        entity: str,
        record_key: str,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "entities.read")
        model = cls._model(admin, entity)
        row = await session.get(model, tuple(_decode_record_key(model, record_key)))
        if row is None:
            raise LookupError("Entity record not found")
        return cls._row_view(entity, model, row)

    @classmethod
    async def update(
        cls,
        session: AsyncSession,
        *,
        admin: AdminAccount,
        entity: str,
        record_key: str,
        changes: dict[str, Any],
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
        step_up_valid: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(
            admin,
            "entities.update",
            confirmed=confirmed,
            step_up_valid=step_up_valid,
        )
        model = cls._model(admin, entity)
        editable = {column.key: column for column in _editable_columns(entity, model)}
        if not editable:
            raise ValueError("Entity is read-only; use a domain admin action")
        if not changes:
            raise ValueError("No entity changes supplied")
        unknown = sorted(set(changes) - set(editable))
        if unknown:
            raise ValueError(f"Fields are not editable: {', '.join(unknown)}")
        normalized = {name: _coerce(editable[name], value) for name, value in changes.items()}

        async def operation() -> dict[str, Any]:
            mapper = sa_inspect(model)
            key_values = _decode_record_key(model, record_key)
            conditions = [
                column == value
                for column, value in zip(mapper.primary_key, key_values, strict=True)
            ]
            row = await session.scalar(select(model).where(*conditions).with_for_update())
            if row is None:
                raise LookupError("Entity record not found")
            for name, value in normalized.items():
                setattr(row, name, value)
            await session.flush()
            return cls._row_view(entity, model, row)

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="entities.update",
            target_id=f"{entity}:{record_key}",
            request_payload={"entity": entity, "changes": normalized},
            operation=operation,
        )
