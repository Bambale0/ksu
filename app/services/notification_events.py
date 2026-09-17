from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.db.models import (
    Generation,
    Notification,
    PartnerPromoProgramConfig,
    PartnerWithdrawal,
    Payment,
    ReferralRelation,
    ReferralReward,
    SupportMessage,
    SupportTicket,
    User,
    WalletTransaction,
)
from app.db.notification_models import NotificationDelivery
from app.services.referral_notification_copy import (
    referral_joined_copy,
    referral_topup_copy,
)


def _money(value: Decimal | object) -> str:
    try:
        return f"{Decimal(value):.2f}".rstrip("0").rstrip(".")
    except Exception:  # noqa: BLE001 - notification copy must not break the business flush
        return str(value)


def _add_notification(
    session: Session,
    *,
    user_id: uuid.UUID,
    kind: str,
    title: str,
    body: str,
    generation_id: uuid.UUID | None = None,
) -> None:
    # Notification rows always own their UUID. Domain linkage lives in an explicit
    # nullable FK so a generation can emit more than one terminal notification over
    # its lifetime (for example failed -> retry -> succeeded) without a PK collision.
    notification_id = uuid.uuid4()
    session.add(
        Notification(
            id=notification_id,
            user_id=user_id,
            generation_id=generation_id,
            kind=kind,
            title=title,
            body=body,
            is_read=False,
        )
    )
    session.add(
        NotificationDelivery(
            id=uuid.uuid4(),
            notification_id=notification_id,
            channel="telegram",
            purpose="transactional",
            status="pending",
            attempts=0,
        )
    )


def _status_changed(obj: object) -> bool:
    state = inspect(obj)
    return bool(state.attrs.status.history.has_changes())


def _referral_payment_amount(session: Session, reward: ReferralReward) -> Decimal:
    transaction = session.get(WalletTransaction, reward.source_transaction_id)
    if (
        transaction is not None
        and transaction.kind == "payment"
        and transaction.reference_type == "payment"
        and transaction.reference_id
    ):
        try:
            payment = session.get(Payment, uuid.UUID(str(transaction.reference_id)))
        except (TypeError, ValueError, AttributeError):
            payment = None
        if payment is not None and payment.currency.upper() == "RUB":
            amount = Decimal(payment.amount)
            if amount > 0:
                return amount
    percent = Decimal(reward.percent)
    if percent > 0:
        return (Decimal(reward.amount) * Decimal("100") / percent).quantize(Decimal("0.01"))
    return Decimal("0")


def _referral_user(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def _add_referral_joined_notification(session: Session, relation: ReferralRelation) -> None:
    referred = _referral_user(session, relation.referred_user_id)
    notification_copy = referral_joined_copy(
        username=referred.username if referred is not None else None,
        first_name=referred.first_name if referred is not None else None,
        last_name=referred.last_name if referred is not None else None,
    )
    _add_notification(
        session,
        user_id=relation.inviter_user_id,
        kind="referral_joined",
        title=notification_copy.title,
        body=notification_copy.body,
    )


def _add_referral_reward_notification(session: Session, reward: ReferralReward) -> None:
    level = 1 if int(reward.level) == 1 else 2
    source = _referral_user(session, reward.source_user_id)
    payment_amount = _referral_payment_amount(session, reward)
    config = session.get(PartnerPromoProgramConfig, "default")
    fixed_rox = (
        Decimal(config.topup_partner_rox)
        if config is not None and level == 1
        else Decimal("0")
    )
    notification_copy = referral_topup_copy(
        username=source.username if source is not None else None,
        first_name=source.first_name if source is not None else None,
        last_name=source.last_name if source is not None else None,
        payment_amount=payment_amount,
        reward_amount=reward.amount,
        reward_percent=reward.percent,
        fixed_rox=fixed_rox,
        level=level,
    )
    _add_notification(
        session,
        user_id=reward.partner_user_id,
        kind=f"referral_line_{level}_topup",
        title=notification_copy.title,
        body=notification_copy.body,
    )


def _queue_generation_notification(
    session: Session,
    generation: Generation,
    *,
    kind: str,
    title: str,
    body: str,
) -> None:
    generation.telegram_notification_status = "pending"
    generation.telegram_notification_sent_at = None
    generation.telegram_message_id = None
    _add_notification(
        session,
        generation_id=generation.id,
        user_id=generation.user_id,
        kind=kind,
        title=title,
        body=body,
    )


def _before_flush(session: Session, _flush_context: object, _instances: object) -> None:
    for obj in list(session.dirty):
        if isinstance(obj, Generation) and _status_changed(obj):
            if obj.status == "succeeded":
                _queue_generation_notification(
                    session,
                    obj,
                    kind="generation_succeeded",
                    title="Контент готов",
                    body="Генерация завершена. Результат доступен в истории.",
                )
            elif obj.status == "failed":
                _queue_generation_notification(
                    session,
                    obj,
                    kind="generation_failed",
                    title="Генерация не завершилась",
                    body="Задача завершилась с ошибкой. Проверьте историю и статус возврата ROX.",
                )
        elif isinstance(obj, Payment) and _status_changed(obj):
            if obj.status == "succeeded":
                _add_notification(
                    session,
                    user_id=obj.user_id,
                    kind="payment_succeeded",
                    title="Баланс пополнен",
                    body=f"Оплата подтверждена. Начислено {_money(obj.rox_amount)} ROX.",
                )
            elif obj.status in {"refunded", "partially_refunded", "chargeback"}:
                _add_notification(
                    session,
                    user_id=obj.user_id,
                    kind="payment_reversed",
                    title="Изменение по платежу",
                    body="По платежу зарегистрирован возврат или корректировка. Актуальный баланс доступен в кошельке.",
                )
        elif isinstance(obj, PartnerWithdrawal) and _status_changed(obj):
            if obj.status in {"processing", "paid", "rejected", "canceled"}:
                titles = {
                    "processing": "Вывод обрабатывается",
                    "paid": "Вывод выплачен",
                    "rejected": "Вывод отклонён",
                    "canceled": "Вывод отменён",
                }
                _add_notification(
                    session,
                    user_id=obj.user_id,
                    kind=f"partner_withdrawal_{obj.status}",
                    title=titles[obj.status],
                    body=f"Заявка на {_money(obj.amount)} ₽: {obj.status}.",
                )

    for obj in list(session.new):
        if isinstance(obj, ReferralRelation):
            _add_referral_joined_notification(session, obj)
        elif isinstance(obj, ReferralReward):
            _add_referral_reward_notification(session, obj)
        elif isinstance(obj, SupportMessage) and obj.is_admin:
            ticket = session.get(SupportTicket, obj.ticket_id)
            if ticket is not None:
                _add_notification(
                    session,
                    user_id=ticket.user_id,
                    kind="support_reply",
                    title="Ответ поддержки",
                    body="В вашем обращении появился новый ответ.",
                )


def register_notification_events() -> None:
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
