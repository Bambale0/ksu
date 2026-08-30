from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from app.services.admin_daily_stats import (
    AdminDailyStats,
    AdminDailyStatsService,
    GenerationDailyStats,
    UserBalanceDailyStats,
)


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_admin_daily_stats_report_matches_operator_format() -> None:
    now = datetime(2026, 8, 30, 22, 41, tzinfo=UTC)
    report = AdminDailyStatsService.format_report(
        AdminDailyStats(
            generated_at=now,
            window_start=now - timedelta(hours=24),
            generation=GenerationDailyStats(
                successful_24h=23,
                paid_24h=8,
                debited_rox=Decimal("180.00"),
                paid_debit_ok=8,
                paid_debit_bad=0,
            ),
            users=UserBalanceDailyStats(
                users_total=279,
                users_24h=57,
                onboarded_total=62,
                wallets_positive=158,
                can_afford_generation=144,
                wallet_balance_total=Decimal("10923.00"),
            ),
        )
    )

    assert report == (
        "Генерации:\n"
        "\n"
        "- За 24 часа `23` успешных генерации.\n"
        "- Платных по ROX: `8`.\n"
        "- Списано `180 ROX`.\n"
        "- Все `8/8` списались корректно, расхождений нет.\n"
        "\n"
        "Пользователи/балансы:\n"
        "\n"
        "- Всего пользователей: `279`.\n"
        "- Новых за 24 часа: `57`.\n"
        "- Onboarding прошли: `62`.\n"
        "- Кошельков с положительным балансом: `158`.\n"
        "- Могут оплатить генерацию `25 ROX` без пополнения: `144`.\n"
        "- Общий баланс на кошельках: `10923 ROX`."
    )


def test_admin_daily_stats_worker_is_deployed_periodic_and_observable() -> None:
    compose = _read("docker-compose.yml")
    worker = _read("app/workers/admin_daily_stats.py")
    service = _read("app/services/admin_daily_stats.py")
    config = _read("app/core/config.py")
    env = _read(".env.example")
    observability = _read("app/core/observability.py")
    runbook = _read("docs/OPERATIONS_RUNBOOK.md")

    assert "admin-daily-stats-worker:" in compose
    assert "python -m app.workers.admin_daily_stats" in compose
    assert "AdminDailyStatsService.collect" in worker
    assert "AdminDailyStatsService.mark_sent" in worker
    assert "admin_daily_stats_interval_seconds" in worker
    assert "DAILY_STATS_SETTING_KEY" in service
    assert "WalletTransaction.reference_type == \"generation\"" in service
    assert "WalletTransaction.kind == \"generation\"" in service
    assert "WalletTransaction.amount < 0" in service
    assert "admin_daily_stats_enabled: bool = True" in config
    assert "admin_daily_stats_poll_seconds: int = 300" in config
    assert "admin_daily_stats_interval_seconds: int = 86400" in config
    assert "ADMIN_DAILY_STATS_ENABLED=true" in env
    assert "ADMIN_DAILY_STATS_POLL_SECONDS=300" in env
    assert "ADMIN_DAILY_STATS_INTERVAL_SECONDS=86400" in env
    assert "admin-daily-stats-worker" in observability
    assert "admin_daily_stats_worker_loop_error" in observability
    assert "admin-daily-stats-worker" in runbook
