from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ReferralNotificationCopy:
    title: str
    body: str


def _money(value: Decimal | object) -> str:
    try:
        return f"{Decimal(value):.2f}".rstrip("0").rstrip(".")
    except Exception:  # noqa: BLE001 - notification copy must never block a business event
        return str(value)


def referral_user_label(
    *,
    username: str | None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> str:
    clean_username = (username or "").strip().lstrip("@")
    if clean_username:
        return f"@{clean_username}"

    display_name = " ".join(
        part.strip()
        for part in (first_name or "", last_name or "")
        if part and part.strip()
    ).strip()
    return display_name or "Пользователь ROXY"


def referral_joined_copy(
    *,
    username: str | None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> ReferralNotificationCopy:
    label = referral_user_label(
        username=username,
        first_name=first_name,
        last_name=last_name,
    )
    return ReferralNotificationCopy(
        title="🎉 Новый реферал",
        body=f"👤 {label}",
    )


def referral_topup_copy(
    *,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    payment_amount: Decimal | object,
    reward_amount: Decimal | object,
    reward_percent: Decimal | object,
    fixed_rox: Decimal | object,
    level: int,
) -> ReferralNotificationCopy:
    label = referral_user_label(
        username=username,
        first_name=first_name,
        last_name=last_name,
    )
    normalized_level = 1 if int(level) == 1 else 2
    title = "💰 Пополнение реферала"
    if normalized_level == 2:
        title = "💰 Пополнение реферала · 2-я линия"

    lines = [
        f"👤 {label}",
        f"💳 Пополнение: {_money(payment_amount)} ₽",
        f"💵 Вам: +{_money(reward_amount)} ₽ ({_money(reward_percent)}%)",
    ]
    fixed_rox_amount = Decimal(fixed_rox)
    if normalized_level == 1 and fixed_rox_amount > 0:
        lines.append(f"💎 +{_money(fixed_rox_amount)} ROX")

    return ReferralNotificationCopy(title=title, body="\n".join(lines))
