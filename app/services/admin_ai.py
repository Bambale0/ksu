from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAccount
from app.services.admin_policy import AdminPolicy
from app.services.admin_reporting import AdminReportingService


class AdminAiService:
    """Operational copilot brief over authoritative admin metrics.

    KSU does not currently configure a separate text-LLM provider for privileged
    operations. Keep this service deterministic and read-only instead of leaking
    admin data to an unconfigured external model. A future provider adapter can
    replace `_recommendations` without changing Telegram/Web transports.
    """

    @staticmethod
    async def brief(session: AsyncSession, *, admin: AdminAccount) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "ai_admin.use")
        summary = await AdminReportingService.summary(session, admin=admin)
        recommendations: list[dict[str, str]] = []
        failed = int(summary["generations"]["failed"])
        open_tickets = int(summary["support"]["open"])
        withdrawals = int(summary["withdrawals"]["pending_or_processing"])
        active_generations = int(summary["generations"]["active"])
        if failed:
            recommendations.append(
                {
                    "priority": "high" if failed >= 10 else "medium",
                    "action": f"Проверить {failed} неуспешных генераций и provider errors.",
                }
            )
        if open_tickets:
            recommendations.append(
                {
                    "priority": "high" if open_tickets >= 20 else "medium",
                    "action": f"Разобрать {open_tickets} открытых обращений поддержки.",
                }
            )
        if withdrawals:
            recommendations.append(
                {
                    "priority": "high" if withdrawals >= 10 else "medium",
                    "action": f"Проверить {withdrawals} выплат партнёрам в очереди.",
                }
            )
        if active_generations >= 100:
            recommendations.append(
                {
                    "priority": "medium",
                    "action": f"Очередь генераций высокая: сейчас активно {active_generations}.",
                }
            )
        if not recommendations:
            recommendations.append(
                {
                    "priority": "low",
                    "action": "Критичных операционных сигналов по текущему summary нет.",
                }
            )
        return {"summary": summary, "recommendations": recommendations}
