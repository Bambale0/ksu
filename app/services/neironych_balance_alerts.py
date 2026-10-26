"""Read-only Neironych partner balance monitoring with durable owner-only alerts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AdminAccount, Notification, User
from app.services.notifications import NotificationService

logger = logging.getLogger(__name__)

_LOW_KIND = "neironych_balance_low"
_RECOVERED_KIND = "neironych_balance_recovered"
_EPISODE_KINDS = (_LOW_KIND, _RECOVERED_KIND)
_BALANCE_LOCK = 9183001000  # Stable Postgres advisory lock namespace for this one provider.


class NeironychBalanceResponseError(ValueError):
    """Balance was not verifiably obtained; never interpret this as a zero balance."""


@dataclass(frozen=True, slots=True)
class NeironychBalanceSnapshot:
    cash_rub: Decimal
    available_rub: Decimal


def _rub_amount(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise NeironychBalanceResponseError("Neironych balance has an invalid numeric representation")
    serialized = str(value)
    if len(serialized) > 64:
        raise NeironychBalanceResponseError("Neironych balance exceeds accepted precision")
    try:
        amount = Decimal(serialized)
    except (InvalidOperation, ValueError) as exc:
        raise NeironychBalanceResponseError("Neironych balance is not numeric") from exc
    # Upstream cash is NUMERIC(18,2); cap both exponents and magnitude BEFORE
    # formatting any fixed-point value into a Telegram notification.
    exponent = amount.as_tuple().exponent if amount.is_finite() else None
    if (
        not amount.is_finite()
        or not isinstance(exponent, int)
        or not -6 <= exponent <= 16
        or abs(amount) > Decimal("9999999999999999.99")
    ):
        raise NeironychBalanceResponseError("Neironych balance is outside accepted RUB range")
    return amount


def _bootstrap_owner_ids() -> set[int]:
    raw = settings.admin_bootstrap_telegram_ids.split(",")
    return {int(item.strip()) for item in raw if item.strip().isdigit() and int(item.strip()) > 0}


class NeironychBalanceAlertService:
    @staticmethod
    async def fetch(*, client: httpx.AsyncClient | None = None) -> NeironychBalanceSnapshot:
        """Read own partner balance. No admin key, no user wallet and no paid POST."""
        key = settings.neironych_api_key.strip()
        if not key:
            raise NeironychBalanceResponseError("Neironych partner API key is not configured")
        base = settings.neironych_api_base_url.rstrip("/")
        parsed = urlsplit(base)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise NeironychBalanceResponseError("Neironych API must have a trusted HTTPS base URL")
        endpoint = f"{base}/v1/balance"
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(8.0, connect=3.0),
                follow_redirects=False, trust_env=False,
            )
        assert client is not None
        try:
            response = await client.get(
                endpoint, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}
            )
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as exc:
                raise NeironychBalanceResponseError("Neironych balance response was not JSON") from exc
            if not isinstance(payload, dict):
                raise NeironychBalanceResponseError("Neironych balance response is not a JSON object")
            if not isinstance(payload.get("partner_id"), str) or not payload["partner_id"]:
                raise NeironychBalanceResponseError("Neironych balance response has no partner identity")
            return NeironychBalanceSnapshot(
                cash_rub=_rub_amount(payload.get("balance_rub")),
                available_rub=_rub_amount(payload.get("available_balance_rub")),
            )
        finally:
            if own_client:
                await client.aclose()

    @staticmethod
    async def authorized_owner(session: AsyncSession, user_id: object) -> bool:
        """Recheck the live bootstrap owner scope before exposing balance text."""
        recipients = _bootstrap_owner_ids()
        if not recipients:
            return False
        owner_id = await session.scalar(
            select(AdminAccount.id)
            .join(User, User.id == AdminAccount.user_id)
            .where(
                User.id == user_id,
                User.telegram_id.in_(recipients),
                User.is_active.is_(True),
                AdminAccount.is_active.is_(True),
                AdminAccount.role == "owner",
            )
        )
        return owner_id is not None

    @staticmethod
    async def poll_once() -> int:
        """Serialize sampling + transition, not merely persistence of the alert.

        An older delayed HTTP response cannot overwrite a newer sample from an
        overlapping worker, because all GETs for this provider occur under the
        same transaction-scoped lock.
        """
        from app.db.session import SessionFactory

        async with SessionFactory() as session:
            await session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": _BALANCE_LOCK})
            snapshot = await NeironychBalanceAlertService.fetch()
            count = await NeironychBalanceAlertService.enqueue(session, snapshot)
            await session.commit()
            return count

    @staticmethod
    async def enqueue(session: AsyncSession, snapshot: NeironychBalanceSnapshot) -> int:
        """Queue only state transitions, serializing concurrent checks across workers.

        The last persisted operational Notification is the episode state.
        NotificationService creates the inbox record and Telegram delivery
        together in this transaction. The caller commits/rolls back atomically.
        """
        threshold = Decimal(settings.neironych_balance_alert_threshold_rub)
        if not snapshot.cash_rub.is_finite() or not snapshot.available_rub.is_finite():
            raise NeironychBalanceResponseError("Balance is not finite")
        owners = _bootstrap_owner_ids()
        if not owners:
            logger.warning("neironych_balance_alert_no_bootstrap_owner_configured")
            return 0

        # The advisory xact lock serializes checks across duplicated workers or
        # overlapping restarts; the notification history survives worker restarts.
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": _BALANCE_LOCK})
        recipients = list((await session.scalars(
            select(User)
            .join(AdminAccount, AdminAccount.user_id == User.id)
            .where(
                User.telegram_id.in_(owners),
                User.is_active.is_(True),
                AdminAccount.is_active.is_(True),
                AdminAccount.role == "owner",
            )
        )).all())
        if not recipients:
            logger.warning("neironych_balance_alert_no_authorized_recipient")
            return 0

        low = snapshot.cash_rub <= threshold
        count = 0
        for user in recipients:
            last = await session.scalar(
                select(Notification)
                .where(Notification.user_id == user.id, Notification.kind.in_(_EPISODE_KINDS))
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(1)
            )
            if low and (last is None or last.kind != _LOW_KIND):
                title = "⚠️ Нейроныч: низкий баланс"
                body = (
                    f"Баланс API Нейроныча: {snapshot.cash_rub:.2f} ₽. "
                    f"Порог предупреждения: {threshold:.2f} ₽. Пополните счёт провайдера."
                )
                kind = _LOW_KIND
            elif not low and last is not None and last.kind == _LOW_KIND:
                title = "✅ Нейроныч: баланс восстановлен"
                body = (
                    f"Баланс API Нейроныча: {snapshot.cash_rub:.2f} ₽. "
                    f"Выше порога {threshold:.2f} ₽. Повторное предупреждение снова включено."
                )
                kind = _RECOVERED_KIND
            else:
                continue
            await NotificationService.create(
                session, user_id=user.id, kind=kind, title=title, body=body, purpose="transactional"
            )
            count += 1
            logger.info(
                "neironych_balance_alert_queued kind=%s cash_rub=%s threshold_rub=%s",
                kind, str(snapshot.cash_rub), str(threshold),
            )
        return count
