from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation, Notification, PartnerWithdrawal, Payment, SupportTicket, User, Wallet
from app.db.onboarding_models import UserOnboarding
from app.db.social_models import UserSubscription
from app.services.credits import InternalCreditService
from app.services.onboarding import OnboardingService
from app.services.profile_preferences import ProfilePreferenceService
from app.services.referrals import ReferralService


class AccountProfileService:
    @staticmethod
    async def overview(session: AsyncSession, user: User) -> dict[str, Any]:
        wallet = await session.get(Wallet, user.id)
        credits = Decimal(wallet.balance if wallet is not None else 0)

        generation_rows = (
            await session.execute(
                select(Generation.status, func.count())
                .where(Generation.user_id == user.id)
                .group_by(Generation.status)
            )
        ).all()
        generations = {str(status): int(count) for status, count in generation_rows}

        payment_rows = (
            await session.execute(
                select(
                    Payment.currency,
                    Payment.status,
                    func.count(),
                    func.coalesce(func.sum(Payment.amount), 0),
                    func.coalesce(func.sum(Payment.rox_amount), 0),
                )
                .where(Payment.user_id == user.id)
                .group_by(Payment.currency, Payment.status)
            )
        ).all()
        payment_currencies: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "successful_count": 0, "successful_amount": Decimal("0"), "credited": Decimal("0"), "statuses": {}}
        )
        for currency, status, count, amount, credited in payment_rows:
            bucket = payment_currencies[str(currency).upper()]
            bucket["count"] += int(count)
            bucket["statuses"][str(status)] = int(count)
            if str(status) in {"succeeded", "partially_refunded", "refunded"}:
                bucket["successful_count"] += int(count)
                bucket["successful_amount"] += Decimal(amount)
                bucket["credited"] += Decimal(credited)

        support_rows = (
            await session.execute(
                select(SupportTicket.status, func.count())
                .where(SupportTicket.user_id == user.id)
                .group_by(SupportTicket.status)
            )
        ).all()
        support = {str(status): int(count) for status, count in support_rows}

        withdrawal_rows = (
            await session.execute(
                select(PartnerWithdrawal.status, func.count())
                .where(PartnerWithdrawal.user_id == user.id)
                .group_by(PartnerWithdrawal.status)
            )
        ).all()
        withdrawals = {str(status): int(count) for status, count in withdrawal_rows}

        following = int(
            (
                await session.scalar(
                    select(func.count()).select_from(UserSubscription).where(
                        UserSubscription.subscriber_user_id == user.id
                    )
                )
            )
            or 0
        )
        followers = int(
            (
                await session.scalar(
                    select(func.count()).select_from(UserSubscription).where(
                        UserSubscription.author_user_id == user.id
                    )
                )
            )
            or 0
        )
        unread = int(
            (
                await session.scalar(
                    select(func.count()).select_from(Notification).where(
                        Notification.user_id == user.id,
                        Notification.is_read.is_(False),
                    )
                )
            )
            or 0
        )

        referral = await ReferralService.stats(session, user.id)
        preferences = await ProfilePreferenceService.get_or_create(session, user.id)
        onboarding = await session.get(UserOnboarding, user.id)
        current_onboarding_version = OnboardingService.current_version()
        withdrawable_rox = InternalCreditService.credits_for(referral["available"])
        pending_withdrawable_rox = InternalCreditService.credits_for(referral["pending"])

        return {
            "account": {
                "id": str(user.id),
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "language_code": user.language_code,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat(),
            },
            "balance": {
                # `credits` stays for API compatibility; the public product unit is ROX.
                "credits": str(credits),
                "bonus_rox": str(credits),
                "withdrawable_rox": str(withdrawable_rox),
                "rub_accounting_equivalent": str(InternalCreditService.rubles_for(credits)),
                "rub_per_credit": str(InternalCreditService.rub_per_credit()),
                "rub_per_rox": str(InternalCreditService.rub_per_credit()),
            },
            "generations": {
                "total": sum(generations.values()),
                "statuses": generations,
            },
            "payments": {
                "total": sum(int(bucket["count"]) for bucket in payment_currencies.values()),
                "currencies": {
                    currency: {
                        "count": int(bucket["count"]),
                        "successful_count": int(bucket["successful_count"]),
                        "successful_amount": str(bucket["successful_amount"]),
                        "credited": str(bucket["credited"]),
                        "credited_rox": str(bucket["credited"]),
                        "statuses": bucket["statuses"],
                    }
                    for currency, bucket in sorted(payment_currencies.items())
                },
            },
            "support": {
                "total": sum(support.values()),
                "statuses": support,
            },
            "partner": {
                "first_line": int(referral["first_line"]),
                "second_line": int(referral["second_line"]),
                "available_rub": str(referral["available"]),
                "pending_rub": str(referral["pending"]),
                "withdrawable_rox": str(withdrawable_rox),
                "pending_withdrawable_rox": str(pending_withdrawable_rox),
                "withdrawals": withdrawals,
            },
            "social": {"following": following, "followers": followers},
            "notifications": {"unread": unread},
            "onboarding": {
                "enabled": settings.onboarding_enabled,
                "current_version": current_onboarding_version,
                "completed_version": onboarding.completed_version if onboarding else None,
                "completed_at": onboarding.completed_at.isoformat() if onboarding else None,
                "is_current": bool(
                    not settings.onboarding_enabled
                    or (onboarding and onboarding.completed_version == current_onboarding_version)
                ),
            },
            "preferences": {
                "ui_language": preferences.ui_language,
                "notifications_enabled": preferences.notifications_enabled,
                "marketing_notifications": preferences.marketing_notifications,
                "profile_discoverable": preferences.profile_discoverable,
            },
        }

    @staticmethod
    def text(overview: dict[str, Any]) -> str:
        account = overview["account"]
        balance = overview["balance"]
        generations = overview["generations"]
        payments = overview["payments"]
        support = overview["support"]
        partner = overview["partner"]
        social = overview["social"]
        notifications = overview["notifications"]
        onboarding = overview["onboarding"]

        name = " ".join(filter(None, [account.get("first_name"), account.get("last_name")])) or "—"
        username = f"@{account['username']}" if account.get("username") else "—"
        payment_lines = []
        for currency, bucket in payments["currencies"].items():
            payment_lines.append(
                f"  • {currency}: {bucket['successful_count']} успешных · {bucket['successful_amount']} {currency} · +{bucket['credited']} ROX"
            )
        payment_text = "\n".join(payment_lines) if payment_lines else "  • платежей пока нет"
        statuses = generations["statuses"]
        active_generations = sum(int(statuses.get(key, 0)) for key in ("queued", "retry", "submitting", "generating"))

        return (
            "👤 Профиль\n\n"
            f"Имя: {name}\n"
            f"Username: {username}\n"
            f"Telegram ID: {account['telegram_id']}\n"
            f"ID аккаунта: {account['id']}\n"
            f"Язык Telegram: {account.get('language_code') or '—'}\n"
            f"Регистрация: {account['created_at']}\n"
            f"Статус: {'активен' if account['is_active'] else 'ограничен'}\n\n"
            "💎 Мои ROX\n"
            f"🟣 Бонусные ROX: {balance['bonus_rox']}\n"
            f"🟢 Выводимые ROX: {balance['withdrawable_rox']}\n"
            "1 ROX = 1 ₽\n\n"
            "✨ Генерации\n"
            f"Всего: {generations['total']} · готово: {statuses.get('succeeded', 0)} · активных: {active_generations} · ошибок: {statuses.get('failed', 0)}\n\n"
            "💳 Пополнения\n"
            f"{payment_text}\n\n"
            "🆘 Поддержка\n"
            f"Обращений: {support['total']} · открыто: {support['statuses'].get('open', 0)} · в работе: {support['statuses'].get('in_progress', 0)}\n\n"
            "👥 Заработать\n"
            f"1 линия: {partner['first_line']} · 2 линия: {partner['second_line']}\n"
            f"Доступно к выводу: {partner['withdrawable_rox']} ROX · в ожидании: {partner['pending_withdrawable_rox']} ROX\n\n"
            "👥 Социальное\n"
            f"Подписки: {social['following']} · подписчики: {social['followers']}\n"
            f"Непрочитанных уведомлений: {notifications['unread']}\n"
            f"Onboarding: {'актуален' if onboarding['is_current'] else 'нужно пройти'}"
        )
