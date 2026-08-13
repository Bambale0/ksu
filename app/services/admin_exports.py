from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any, Literal

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAccount, PartnerWithdrawal, Payment
from app.services.admin_policy import AdminPolicy

ExportKind = Literal["payments", "withdrawals"]
ExportFormat = Literal["csv", "xlsx"]


class AdminExportService:
    MAX_ROWS = 10_000

    @staticmethod
    async def _rows(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        kind: ExportKind,
    ) -> tuple[list[str], list[list[Any]]]:
        AdminPolicy.require_permission(admin, "finance.read")
        if kind == "payments":
            items = list(
                (
                    await session.scalars(
                        select(Payment)
                        .order_by(Payment.created_at.desc())
                        .limit(AdminExportService.MAX_ROWS)
                    )
                ).all()
            )
            headers = [
                "id",
                "user_id",
                "provider",
                "external_id",
                "amount",
                "currency",
                "credits",
                "status",
                "created_at",
                "updated_at",
            ]
            rows = [
                [
                    str(item.id),
                    str(item.user_id),
                    item.provider,
                    item.external_id or "",
                    str(item.amount),
                    item.currency,
                    str(item.rox_amount),
                    item.status,
                    item.created_at.isoformat(),
                    item.updated_at.isoformat(),
                ]
                for item in items
            ]
            return headers, rows

        items = list(
            (
                await session.scalars(
                    select(PartnerWithdrawal)
                    .order_by(PartnerWithdrawal.created_at.desc())
                    .limit(AdminExportService.MAX_ROWS)
                )
            ).all()
        )
        headers = ["id", "user_id", "amount", "status", "created_at", "updated_at"]
        rows = [
            [
                str(item.id),
                str(item.user_id),
                str(item.amount),
                item.status,
                item.created_at.isoformat(),
                item.updated_at.isoformat(),
            ]
            for item in items
        ]
        return headers, rows

    @classmethod
    async def export(
        cls,
        session: AsyncSession,
        *,
        admin: AdminAccount,
        kind: ExportKind,
        format: ExportFormat,
    ) -> tuple[str, str, bytes]:
        headers, rows = await cls._rows(session, admin=admin, kind=kind)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        if format == "csv":
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer)
            writer.writerow(headers)
            writer.writerows(rows)
            content = buffer.getvalue().encode("utf-8-sig")
            return f"{kind}-{stamp}.csv", "text/csv; charset=utf-8", content

        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet(title=kind[:31])
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        binary = io.BytesIO()
        workbook.save(binary)
        return (
            f"{kind}-{stamp}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            binary.getvalue(),
        )
