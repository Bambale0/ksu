"""redenominate legacy 10-RUB credits to public 1-RUB ROX"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0023_roxy_one_ruble_denomination"
down_revision = "0022_batch_generation_commands"
branch_labels = None
depends_on = None

_FACTOR = Decimal("10")


def _scale_number(value: Any, factor: Decimal) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    scaled = number * factor
    if isinstance(value, str):
        return format(scaled.normalize(), "f")
    if scaled == scaled.to_integral_value():
        return int(scaled)
    return float(scaled)


def _scale_prompt_costs(payload: Any, factor: Decimal) -> Any:
    if not isinstance(payload, dict):
        return payload
    prompt_costs = payload.get("prompt_costs")
    if not isinstance(prompt_costs, dict):
        return payload
    next_payload = dict(payload)
    next_costs: dict[str, Any] = {}
    for key, value in prompt_costs.items():
        if isinstance(value, dict):
            next_value = dict(value)
            if "credits" in next_value:
                next_value["credits"] = _scale_number(next_value["credits"], factor)
            next_costs[key] = next_value
        else:
            next_costs[key] = _scale_number(value, factor)
    next_payload["prompt_costs"] = next_costs
    return next_payload


def _scale_columns(factor: Decimal) -> None:
    f = str(factor)
    statements = (
        f"UPDATE wallets SET balance = balance * {f}",
        f"UPDATE wallet_transactions SET amount = amount * {f}, balance_before = balance_before * {f}, balance_after = balance_after * {f}",
        f"UPDATE promo_codes SET reward_amount = reward_amount * {f}",
        f"UPDATE generations SET cost_rox = cost_rox * {f}",
        f"UPDATE payments SET rox_amount = rox_amount * {f}",
        f"UPDATE payment_reversals SET credits = credits * {f}",
        f"UPDATE prompt_tool_tasks SET cost_credits = cost_credits * {f}",
        f"UPDATE batch_generation_jobs SET initial_cost_rox = initial_cost_rox * {f}, total_charged_rox = total_charged_rox * {f}",
    )
    for statement in statements:
        op.execute(sa.text(statement))


def _scale_tariff_prompt_costs(factor: Decimal) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, payload FROM tariff_versions")).mappings().all()
    for row in rows:
        payload = _scale_prompt_costs(row["payload"], factor)
        if payload == row["payload"]:
            continue
        bind.execute(
            sa.text("UPDATE tariff_versions SET payload = :payload WHERE id = :id"),
            {"payload": payload, "id": row["id"]},
        )


def upgrade() -> None:
    _scale_columns(_FACTOR)
    _scale_tariff_prompt_costs(_FACTOR)


def downgrade() -> None:
    inverse = Decimal("1") / _FACTOR
    _scale_tariff_prompt_costs(inverse)
    _scale_columns(inverse)
