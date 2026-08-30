from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import AdminRuntimeSetting
from app.db.models import AdminAccount, Generation, User, Wallet, WalletTransaction
from app.db.onboarding_models import UserOnboarding


DAILY_STATS_SETTING_KEY = "admin_daily_stats_last_sent"


@dataclass(frozen=True)
class GenerationDailyStats:
    successful_24h: int
    paid_24h: int
    debited_rox: Decimal
    paid_debit_ok: int
    paid_debit_bad: int


@dataclass(frozen=True)
class UserBalanceDailyStats:
    users_total: int
    users_24h: int
    onboarded_total: int
    wallets_positive: int
    can_afford_generation: int
    wallet_balance_total: Decimal


@dataclass(frozen=True)
class AdminDailyStats:
    generated_at: datetime
    window_start: datetime
    generation: GenerationDailyStats
    users: UserBalanceDailyStats


def _count(value: int | None) -> int:
    return int(value or 0)


def _decimal(value: Decimal | int | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


def _format_rox(value: Decimal) -> str:
    value = value.quantize(Decimal("0.01"))
    if value == value.to_integral_value():
        return str(int(value))
    return str(value.normalize())


class AdminDailyStatsService:
    @staticmethod
    async def collect(
        session: AsyncSession,
        *,
        now: datetime | None = None,
        generation_price_rox: Decimal = Decimal("25"),
    ) -> AdminDailyStats:
        generated_at = now or datetime.now(UTC)
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=UTC)
        window_start = generated_at - timedelta(hours=24)

        successful_24h = _count(
            await session.scalar(
                select(func.count())
                .select_from(Generation)
                .where(
                    Generation.created_at >= window_start,
                    Generation.status == "succeeded",
                )
            )
        )
        paid_rows = list(
            (
                await session.execute(
                    select(Generation.id, Generation.cost_rox).where(
                        Generation.created_at >= window_start,
                        Generation.status == "succeeded",
                        Generation.cost_rox > 0,
                    )
                )
            ).all()
        )
        costs_by_generation = {str(row.id): Decimal(row.cost_rox) for row in paid_rows}
        paid_generation_ids = list(costs_by_generation)
        debits_by_generation: dict[str, Decimal] = {
            generation_id: Decimal("0") for generation_id in paid_generation_ids
        }
        if costs_by_generation:
            debit_rows = list(
                (
                    await session.execute(
                        select(WalletTransaction.reference_id, WalletTransaction.amount).where(
                            WalletTransaction.reference_type == "generation",
                            WalletTransaction.kind == "generation",
                            WalletTransaction.amount < 0,
                            WalletTransaction.reference_id.in_(paid_generation_ids),
                        )
                    )
                ).all()
            )
            for reference_id, amount in debit_rows:
                if reference_id is None:
                    continue
                debits_by_generation[reference_id] = debits_by_generation.get(
                    reference_id,
                    Decimal("0"),
                ) - Decimal(amount)

        paid_debit_ok = sum(
            1
            for generation_id, expected_cost in costs_by_generation.items()
            if debits_by_generation.get(generation_id, Decimal("0")) == expected_cost
        )
        paid_24h = len(costs_by_generation)
        paid_debit_bad = paid_24h - paid_debit_ok
        debited_rox = sum(debits_by_generation.values(), Decimal("0"))

        users_total = _count(await session.scalar(select(func.count()).select_from(User)))
        users_24h = _count(
            await session.scalar(
                select(func.count()).select_from(User).where(User.created_at >= window_start)
            )
        )
        onboarded_total = _count(
            await session.scalar(select(func.count()).select_from(UserOnboarding))
        )
        wallets_positive = _count(
            await session.scalar(
                select(func.count()).select_from(Wallet).where(Wallet.balance > 0)
            )
        )
        can_afford_generation = _count(
            await session.scalar(
                select(func.count())
                .select_from(Wallet)
                .where(Wallet.balance >= generation_price_rox)
            )
        )
        wallet_balance_total = _decimal(await session.scalar(select(func.sum(Wallet.balance))))

        return AdminDailyStats(
            generated_at=generated_at,
            window_start=window_start,
            generation=GenerationDailyStats(
                successful_24h=successful_24h,
                paid_24h=paid_24h,
                debited_rox=debited_rox,
                paid_debit_ok=paid_debit_ok,
                paid_debit_bad=paid_debit_bad,
            ),
            users=UserBalanceDailyStats(
                users_total=users_total,
                users_24h=users_24h,
                onboarded_total=onboarded_total,
                wallets_positive=wallets_positive,
                can_afford_generation=can_afford_generation,
                wallet_balance_total=wallet_balance_total,
            ),
        )

    @staticmethod
    def format_report(stats: AdminDailyStats) -> str:
        generation = stats.generation
        users = stats.users
        if generation.paid_debit_bad:
            debit_line = (
                f"- Списались корректно `{generation.paid_debit_ok}/{generation.paid_24h}`, "
                f"расхождений: `{generation.paid_debit_bad}`."
            )
        else:
            debit_line = (
                f"- Все `{generation.paid_debit_ok}/{generation.paid_24h}` списались "
                "корректно, расхождений нет."
            )
        return "\n".join(
            (
                "Генерации:",
                "",
                f"- За 24 часа `{generation.successful_24h}` успешных генерации.",
                f"- Платных по ROX: `{generation.paid_24h}`.",
                f"- Списано `{_format_rox(generation.debited_rox)} ROX`.",
                debit_line,
                "",
                "Пользователи/балансы:",
                "",
                f"- Всего пользователей: `{users.users_total}`.",
                f"- Новых за 24 часа: `{users.users_24h}`.",
                f"- Onboarding прошли: `{users.onboarded_total}`.",
                f"- Кошельков с положительным балансом: `{users.wallets_positive}`.",
                f"- Могут оплатить генерацию `25 ROX` без пополнения: `{users.can_afford_generation}`.",
                f"- Общий баланс на кошельках: `{_format_rox(users.wallet_balance_total)} ROX`.",
            )
        )

    @staticmethod
    async def active_admin_chat_ids(session: AsyncSession) -> list[int]:
        rows = list(
            (
                await session.execute(
                    select(User.telegram_id)
                    .join(AdminAccount, AdminAccount.user_id == User.id)
                    .where(AdminAccount.is_active.is_(True), User.is_active.is_(True))
                    .order_by(AdminAccount.created_at.asc())
                )
            ).scalars()
        )
        return list(dict.fromkeys(int(row) for row in rows))

    @staticmethod
    async def active_admin_for_marker(session: AsyncSession) -> AdminAccount | None:
        admin = await session.scalar(
            select(AdminAccount)
            .where(AdminAccount.is_active.is_(True))
            .order_by(AdminAccount.created_at.asc())
            .limit(1)
        )
        return admin

    @staticmethod
    async def due_to_send(
        session: AsyncSession,
        *,
        now: datetime | None = None,
        interval_seconds: int = 86400,
    ) -> bool:
        current = now or datetime.now(UTC)
        marker = await session.get(AdminRuntimeSetting, DAILY_STATS_SETTING_KEY)
        if marker is None:
            return True
        raw_sent_at = (marker.value or {}).get("last_sent_at")
        if not isinstance(raw_sent_at, str):
            return True
        try:
            last_sent_at = datetime.fromisoformat(raw_sent_at)
        except ValueError:
            return True
        if last_sent_at.tzinfo is None:
            last_sent_at = last_sent_at.replace(tzinfo=UTC)
        return current - last_sent_at >= timedelta(seconds=interval_seconds)

    @staticmethod
    async def mark_sent(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        sent_at: datetime,
        chat_ids: list[int],
    ) -> None:
        marker = await session.get(AdminRuntimeSetting, DAILY_STATS_SETTING_KEY)
        value = {
            "last_sent_at": sent_at.isoformat(),
            "chat_count": len(chat_ids),
            "chat_ids": [str(chat_id) for chat_id in chat_ids],
        }
        if marker is None:
            marker = AdminRuntimeSetting(
                key=DAILY_STATS_SETTING_KEY,
                value=value,
                updated_by_admin_id=admin.id,
            )
            session.add(marker)
        else:
            marker.value = value
            marker.updated_by_admin_id = admin.id
        await session.flush()
