"""Read-only Neironych partner balance monitoring with durable owner-only alerts."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.observability import request_id_var
from app.db.admin_models import AdminRuntimeSetting
from app.db.models import AdminAccount, Notification, User
from app.services.notifications import NotificationService

logger = logging.getLogger(__name__)

_LOW_KIND = "neironych_balance_low"
_RECOVERED_KIND = "neironych_balance_recovered"
_EPISODE_KINDS = (_LOW_KIND, _RECOVERED_KIND)
BALANCE_NOTIFICATION_KINDS = _EPISODE_KINDS
BALANCE_ALERT_SETTING_KEY = "neironych_balance_alert"
_BALANCE_LOCK = 9183001000  # Stable Postgres advisory lock namespace for this one provider.
_MAX_THRESHOLD_RUB = Decimal("100000000.00")
_MAX_BALANCE_RESPONSE_BYTES = 16 * 1024


class NeironychBalanceResponseError(ValueError):
    """Balance was not verifiably obtained; never interpret this as a zero balance."""


@dataclass(frozen=True, slots=True)
class NeironychBalanceSnapshot:
    cash_rub: Decimal
    available_rub: Decimal


@dataclass(frozen=True, slots=True)
class NeironychBalanceAlertPolicy:
    enabled: bool
    threshold_rub: Decimal
    revision: int

    def payload(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "threshold_rub": f"{self.threshold_rub:.2f}",
            "revision": self.revision,
        }


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


def _threshold_amount(value: object) -> Decimal:
    amount = _rub_amount(value)
    exponent = amount.as_tuple().exponent
    if amount < 0 or amount > _MAX_THRESHOLD_RUB or exponent < -2:
        raise NeironychBalanceResponseError("Neironych alert threshold is outside accepted range")
    return amount.quantize(Decimal("0.01"))


def balance_alert_policy(
    *, enabled: object, threshold_rub: object, revision: object
) -> NeironychBalanceAlertPolicy:
    if not isinstance(enabled, bool):
        raise NeironychBalanceResponseError("Neironych alert enabled flag is invalid")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise NeironychBalanceResponseError("Neironych alert revision is invalid")
    return NeironychBalanceAlertPolicy(
        enabled=enabled,
        threshold_rub=_threshold_amount(threshold_rub),
        revision=revision,
    )


def _bootstrap_owner_ids() -> set[int]:
    raw = settings.admin_bootstrap_telegram_ids.split(",")
    return {int(item.strip()) for item in raw if item.strip().isdigit() and int(item.strip()) > 0}


class NeironychBalanceAlertService:
    @staticmethod
    async def acquire_lock(session: AsyncSession) -> None:
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": _BALANCE_LOCK})

    @staticmethod
    async def policy(session: AsyncSession) -> NeironychBalanceAlertPolicy:
        row = await session.get(
            AdminRuntimeSetting,
            BALANCE_ALERT_SETTING_KEY,
            populate_existing=True,
        )
        if row is None:
            return balance_alert_policy(
                enabled=True,
                threshold_rub=settings.neironych_balance_alert_threshold_rub,
                revision=1,
            )
        value = row.value if isinstance(row.value, dict) else {}
        return balance_alert_policy(
            enabled=value.get("enabled"),
            threshold_rub=value.get("threshold_rub"),
            revision=value.get("revision"),
        )

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
            headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
            if request_id := request_id_var.get():
                headers["X-Request-ID"] = request_id
            async with client.stream("GET", endpoint, headers=headers) as response:
                response.raise_for_status()
                declared_length = response.headers.get("content-length")
                if declared_length is not None:
                    try:
                        declared_bytes = int(declared_length)
                    except ValueError as exc:
                        raise NeironychBalanceResponseError(
                            "Neironych balance response has an invalid content length"
                        ) from exc
                    if declared_bytes < 0 or declared_bytes > _MAX_BALANCE_RESPONSE_BYTES:
                        raise NeironychBalanceResponseError(
                            "Neironych balance response exceeds the accepted size"
                        )
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > _MAX_BALANCE_RESPONSE_BYTES:
                        raise NeironychBalanceResponseError(
                            "Neironych balance response exceeds the accepted size"
                        )
                    body.extend(chunk)
            try:
                payload = json.loads(bytes(body))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
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
    async def is_current_notice(session: AsyncSession, notification: Notification) -> bool:
        """Return false when a retry would contradict a newer balance observation."""
        latest_id = await session.scalar(
            select(Notification.id)
            .where(
                Notification.user_id == notification.user_id,
                Notification.kind.in_(_EPISODE_KINDS),
            )
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(1)
        )
        return latest_id == notification.id

    @staticmethod
    async def poll_once() -> int:
        """Serialize sampling + transition, not merely persistence of the alert.

        An older delayed HTTP response cannot overwrite a newer sample from an
        overlapping worker, because all GETs for this provider occur under the
        same transaction-scoped lock.
        """
        from app.db.session import SessionFactory

        async with SessionFactory() as session:
            await NeironychBalanceAlertService.acquire_lock(session)
            policy = await NeironychBalanceAlertService.policy(session)
            if not policy.enabled:
                return 0
            snapshot = await NeironychBalanceAlertService.fetch()
            count = await NeironychBalanceAlertService._enqueue_locked(session, snapshot, policy)
            await session.commit()
            logger.info(
                "neironych_balance_poll_succeeded cash_rub=%s threshold_rub=%s queued=%s",
                str(snapshot.cash_rub), str(policy.threshold_rub), count,
            )
            return count

    @staticmethod
    async def enqueue(session: AsyncSession, snapshot: NeironychBalanceSnapshot) -> int:
        """Queue only state transitions, serializing concurrent checks across workers.

        The last persisted operational Notification is the episode state.
        NotificationService creates the inbox record and Telegram delivery
        together in this transaction. The caller commits/rolls back atomically.
        """
        await NeironychBalanceAlertService.acquire_lock(session)
        policy = await NeironychBalanceAlertService.policy(session)
        if not policy.enabled:
            return 0
        return await NeironychBalanceAlertService._enqueue_locked(session, snapshot, policy)

    @staticmethod
    async def _enqueue_locked(
        session: AsyncSession,
        snapshot: NeironychBalanceSnapshot,
        policy: NeironychBalanceAlertPolicy,
    ) -> int:
        threshold = policy.threshold_rub
        if not snapshot.cash_rub.is_finite() or not snapshot.available_rub.is_finite():
            raise NeironychBalanceResponseError("Balance is not finite")
        owners = _bootstrap_owner_ids()
        if not owners:
            logger.warning("neironych_balance_alert_no_bootstrap_owner_configured")
            return 0

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
            notice = await NotificationService.create(
                session, user_id=user.id, kind=kind, title=title, body=body, purpose="transactional"
            )
            count += 1
            logger.info(
                "neironych_balance_alert_queued notification_id=%s kind=%s cash_rub=%s threshold_rub=%s",
                str(notice.id), kind, str(snapshot.cash_rub), str(threshold),
            )
        return count
